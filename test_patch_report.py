"""Synthetic files only. No customer recording, MIDI device or network access."""
import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import mido
import patch_report as tool


def file_with(*tracks, kind=None):
    mid = mido.MidiFile(type=(0 if len(tracks)==1 else 1) if kind is None else kind)
    mid.tracks.extend(mido.MidiTrack(track) for track in tracks)
    return mid


def cc(number, value, **kwargs):
    return mido.Message('control_change', control=number, value=value, **kwargs)


class ReportTests(unittest.TestCase):
    def test_raw_program_and_display_bases(self):
        r=tool.report_midi(file_with([mido.Message('program_change',program=0),mido.Message('program_change',program=127)]))
        self.assertEqual([(x['value_raw'],x['program_display_1_based']) for x in r['events']],[(0,1),(127,128)])

    def test_delta_ticks_include_ignored_notes(self):
        r=tool.report_midi(file_with([mido.Message('note_on',time=17),cc(0,3,time=4),mido.Message('note_off',time=9),cc(32,4,time=2)]))
        self.assertEqual([x['tick'] for x in r['events']],[21,32])

    def test_controller_selection_only(self):
        r=tool.report_midi(file_with([cc(0,4),cc(32,7),cc(1,8),cc(64,127),cc(120,0)]))
        self.assertEqual([x['message'] for x in r['events']],['bank_select_msb','bank_select_lsb'])

    def test_channel_filter_preserves_global_counts(self):
        r=tool.report_midi(file_with([cc(0,2,channel=0),mido.Message('program_change',program=3,channel=15)]),channel=16)
        self.assertEqual(r['returned_patch_messages'],1)
        self.assertEqual(r['events'][0]['channel'],16)
        self.assertEqual(r['patch_message_counts_before_filters']['bank_select_msb'],1)

    def test_port_scope_within_track(self):
        r=tool.report_midi(file_with([cc(0,1),mido.MetaMessage('midi_port',port=3),cc(32,5),mido.MetaMessage('midi_port',port=255),cc(0,8)]))
        self.assertEqual([(x['port'],x['port_declared']) for x in r['events']],[(0,False),(3,True),(255,True)])

    def test_port_does_not_leak_between_tracks(self):
        r=tool.report_midi(file_with([mido.MetaMessage('midi_port',port=2),cc(0,3)],[cc(32,5)]))
        self.assertEqual([x['port'] for x in r['events']],[2,0])
        self.assertFalse(any(x['cross_track_same_tick'] for x in r['events']))

    def test_same_tick_other_track_annotated(self):
        r=tool.report_midi(file_with([cc(0,4)],[mido.Message('program_change',program=8)]))
        self.assertTrue(all(x['cross_track_same_tick'] for x in r['events']))
        self.assertEqual(r['cross_track_same_tick_groups_before_filters'],[{'sequence':1,'tick':0,'port':0,'channel':1,'tracks':[1,2]}])

    def test_other_channel_not_tie(self):
        r=tool.report_midi(file_with([cc(0,4,channel=0)],[cc(32,7,channel=1)]))
        self.assertEqual(r['cross_track_same_tick_groups_before_filters'],[])

    def test_same_track_order_not_sorted_by_message_kind(self):
        r=tool.report_midi(file_with([mido.Message('program_change',program=9),cc(32,4),cc(0,2)]))
        self.assertEqual([x['message'] for x in r['events']],['program_change','bank_select_lsb','bank_select_msb'])
        self.assertFalse(any(x['cross_track_same_tick'] for x in r['events']))

    def test_type2_independent_sequences(self):
        r=tool.report_midi(file_with([cc(0,4,time=40)],[cc(32,7,time=2)],kind=2))
        self.assertEqual(r['sequence_mode'],'independent_tracks')
        self.assertEqual([(x['sequence'],x['tick']) for x in r['events']],[(1,40),(2,2)])
        self.assertEqual(r['cross_track_same_tick_groups_before_filters'],[])

    def test_raw_smpte_division_not_treated_as_ppqn(self):
        mid=file_with([cc(0,2)]);mid.ticks_per_beat=-6360
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'smpte.mid';mid.save(p);r=tool.inspect_file(p)
        self.assertEqual(r['time_division_kind'],'smpte_raw')
        self.assertEqual(r['time_division_raw'],-6360)

    def test_empty_patch_inventory_valid(self):
        r=tool.report_midi(file_with([mido.Message('note_on',note=60),mido.Message('note_off',note=60)]))
        self.assertEqual(r['returned_patch_messages'],0)
        out=io.StringIO();tool.write_csv(r,out)
        self.assertEqual(len(out.getvalue().splitlines()),1)

    def test_sysex_payload_not_disclosed(self):
        r=tool.report_midi(file_with([mido.Message('sysex',data=[1,2,3,4]),cc(0,5)]))
        self.assertEqual(r['sysex_messages_not_decoded'],1)
        self.assertNotIn('data',json.dumps(r))

    def test_reset_count_not_interpreted(self):
        r=tool.report_midi(file_with([cc(121,0),cc(0,8)]))
        self.assertEqual(r['reset_all_controllers_messages_not_interpreted'],1)
        self.assertEqual(r['returned_patch_messages'],1)

    def test_filter_tie_knowledge_retained(self):
        r=tool.report_midi(file_with([cc(0,4)],[cc(32,8)]),port=7)
        self.assertEqual(r['events'],[])
        self.assertEqual(len(r['cross_track_same_tick_groups_before_filters']),1)

    def test_invalid_filters(self):
        mid=file_with([cc(0,2)])
        for kwargs in [{'channel':0},{'channel':17},{'port':-1},{'port':256}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):tool.report_midi(mid,**kwargs)

    def test_invalid_track_time(self):
        for value in [-1,0.5]:
            with self.subTest(value=value),self.assertRaises(ValueError):tool.report_midi(file_with([cc(0,2,time=value)]))

    def test_invalid_type0_and_no_tracks(self):
        mid=file_with([cc(0,2)],[cc(32,3)]);mid.type=0
        with self.assertRaises(ValueError):tool.report_midi(mid)
        with self.assertRaises(ValueError):tool.report_midi(mido.MidiFile())

    def test_input_bytes_unchanged_no_outputs_created(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'synthetic.mid';file_with([cc(0,3),mido.Message('program_change',program=8)]).save(p)
            before=hashlib.sha256(p.read_bytes()).hexdigest();tool.inspect_file(p)
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before)
            self.assertEqual([x.name for x in Path(td).iterdir()],['synthetic.mid'])

    def test_bounded_input_read(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'large.mid';p.write_bytes(b'MThd'+b'x'*20)
            with patch.object(tool,'MAX_BYTES',16),self.assertRaisesRegex(ValueError,'read limit'):tool.inspect_file(p)

    def test_cli_invalid_files_are_clean_errors(self):
        with tempfile.TemporaryDirectory() as td:
            for name,data in [('text.mid',b'not midi'),('short.mid',b'MThd'),('broken.mid',b'MThd\0\0\0\x06\0')]:
                p=Path(td)/name;p.write_bytes(data);out=io.StringIO();err=io.StringIO()
                with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=tool.main([str(p)])
                self.assertEqual(code,2);self.assertEqual(out.getvalue(),'');self.assertTrue(err.getvalue().startswith('Cannot inspect'))

    def test_cli_missing_file_is_clean_error(self):
        with tempfile.TemporaryDirectory() as td:
            out=io.StringIO();err=io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=tool.main([str(Path(td)/'missing.mid')])
            self.assertEqual(code,2);self.assertEqual(out.getvalue(),'')

    def test_synthetic_example_matches_actual_cli(self):
        root=Path(__file__).parent
        if not (root/'example.mid').exists():self.skipTest('Example not generated yet')
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=tool.main([str(root/'example.mid')])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out.getvalue()),json.loads((root/'expected-example.json').read_text()))

    def test_actual_cli_nonempty_csv(self):
        root=Path(__file__).parent
        if not (root/'example.mid').exists():self.skipTest('Example not generated yet')
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=tool.main([str(root/'example.mid'),'--format','csv','--channel','1','--port','1'])
        self.assertEqual(code,0)
        rows=list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[2]['message'],'program_change')
        self.assertEqual(rows[2]['program_display_1_based'],'11')
        self.assertEqual(rows[3]['cross_track_same_tick'],'True')

    def test_independent_random_event_oracle(self):
        # Expected rows are recorded during construction, not by rescanning MIDI.
        rng=random.Random(180028)
        for stream in range(100):
            tick=0;port=0;declared=False;messages=[];expected=[]
            for index in range(120):
                delta=rng.randrange(0,18);tick+=delta;kind=rng.randrange(5);chan=rng.randrange(16);value=rng.randrange(128)
                if kind==0:
                    port=rng.randrange(4);declared=True;messages.append(mido.MetaMessage('midi_port',port=port,time=delta));continue
                if kind==1:
                    messages.append(mido.Message('note_on',note=value,channel=chan,time=delta));continue
                number=0 if kind==2 else 32
                msg=cc(number,value,channel=chan,time=delta) if kind in (2,3) else mido.Message('program_change',program=value,channel=chan,time=delta)
                messages.append(msg)
                label={2:'bank_select_msb',3:'bank_select_lsb',4:'program_change'}[kind]
                expected.append({'sequence':1,'tick':tick,'track':1,'event_index':index+1,'port':port,'port_declared':declared,'channel':chan+1,'message':label,'value_raw':value,'program_display_1_based':value+1 if kind==4 else None,'cross_track_same_tick':False})
            with self.subTest(stream=stream):self.assertEqual(tool.report_midi(file_with(messages))['events'],expected)


if __name__=='__main__':unittest.main()
