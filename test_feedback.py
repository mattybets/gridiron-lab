"""Regression checks for snapshot matching and showdown scoring. Run: python test_feedback.py"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import evaluate_contests as ec

class FeedbackTests(unittest.TestCase):
    def test_snapshot_matching_and_captain_multiplier(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'data'/'pregame').mkdir(parents=True)
            (root/'data'/'actuals').mkdir(parents=True)
            snapshot={
                'matchup':'TEST @ TEST','saved_at_utc':'2026-10-18T18:00:00Z',
                'players':[{'name':f'P{i}','team':'A' if i<3 else 'B','projection':10.0} for i in range(6)],
                'lineups':[{'strategy':'gpp','index':1,'projected':65.0,
                    'players':[{'name':f'P{i}','team':'A' if i<3 else 'B',
                                'slot':'CPT' if i==0 else 'FLEX'} for i in range(6)]}]
            }
            actual={'matchup':'TEST @ TEST','players':[
                {'name':f'P{i}','team':'A' if i<3 else 'B','actual_points':float(i+1)}
                for i in range(6)]}
            (root/'data'/'pregame'/'test.json').write_text(json.dumps(snapshot))
            (root/'data'/'actuals'/'test.json').write_text(json.dumps(actual))
            with patch.object(ec,'ROOT',root):
                result=ec.evaluate_snapshots()
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['status'],'evaluated')
            self.assertEqual(result[0]['matched_player_count'],6)
            self.assertEqual(result[0]['evaluated_lineups'][0]['actual_points'],21.5)
            self.assertAlmostEqual(result[0]['mean_absolute_player_error'],6.5)

    def test_calibration_refuses_small_sample(self):
        row={'matchup':'TEST','saved_at_utc':'2026-10-18T18:00:00Z',
             'status':'evaluated','gpp_candidate_count':2,
             'evaluated_lineups':[
                 {'strategy':'gpp','modeled_p90':120,'modeled_mean':95,
                  'projected':98,'modeled_ceiling':130,'actual_points':110},
                 {'strategy':'gpp','modeled_p90':110,'modeled_mean':90,
                  'projected':92,'modeled_ceiling':125,'actual_points':120}]}
        result=ec.fit_ranking([row,row,row])
        self.assertFalse(result['enabled'])
        self.assertEqual(result['validated_games'],1)
        self.assertEqual(result['weights'],ec.DEFAULT_WEIGHTS)

    def test_retrospective_case_excluded_from_calibration(self):
        row={'matchup':'NE @ CHI','saved_at_utc':'2026-10-23T15:37:02Z',
             'status':'evaluated','retrospective_only':True,'gpp_candidate_count':2,
             'evaluated_lineups':[{'strategy':'gpp','modeled_p90':120,'modeled_mean':95,
                 'projected':98,'modeled_ceiling':130,'actual_points':110},
                 {'strategy':'gpp','modeled_p90':110,'modeled_mean':90,
                 'projected':92,'modeled_ceiling':125,'actual_points':120}]}
        result=ec.fit_ranking([row])
        self.assertEqual(result['validated_games'],0)
        self.assertFalse(result['enabled'])

    def test_projection_diagnostics_deduplicates_games(self):
        row={'matchup':'A @ B','saved_at_utc':'2026-10-25T12:00:00Z',
             'status':'evaluated','matched_players':[
                 {'name':'QB A','team':'A','position':'QB','projection':20,'actual_points':12},
                 {'name':'RB B','team':'B','position':'RB','projection':10,'actual_points':14}]}
        out=ec.projection_diagnostics([row,row])
        self.assertEqual(out['independent_games'],1)
        self.assertEqual(out['by_position']['QB']['samples'],1)
        self.assertEqual(out['by_position']['QB']['mean_signed_error'],8)
        self.assertEqual(out['by_position']['RB']['mean_signed_error'],-4)

    def test_position_adjustments_do_not_fit_on_same_game(self):
        row={'matchup':'ONE','saved_at_utc':'2026-10-18T18:00:00Z',
             'status':'evaluated','matched_players':[
                 {'name':'QB','team':'A','position':'QB','projection':20,'actual_points':5}]}
        result=ec.fit_position_adjustments([row,row,row,row])
        self.assertFalse(result['enabled'])
        self.assertEqual(result['validated_games'],1)

    def test_position_adjustments_require_out_of_sample_improvement(self):
        games=[]
        for i in range(4):
            games.append({'matchup':str(i),'saved_at_utc':f'2026-10-1{i}T18:00:00Z',
                          'status':'evaluated','matched_players':[
                              {'name':str(k),'team':'A','position':'QB','projection':20,'actual_points':10}
                              for k in range(10)]})
        result=ec.fit_position_adjustments(games)
        self.assertTrue(result['enabled'])
        self.assertLess(result['adjustments']['QB'],0)

    def test_real_snapshots_are_readable(self):
        rows=ec.evaluate_snapshots()
        self.assertGreaterEqual(len(rows),4)
        for row in rows:
            self.assertGreater(row['player_count'],0)
            self.assertGreater(row['lineup_count'],0)

if __name__=='__main__':
    unittest.main()
