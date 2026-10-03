import math
import unittest
from datetime import date, timedelta
from idx_evidence_lab.issuer_dossier import historical_analogs, walk_forward, net_return, summarize, disclosure_outcomes


def fixture(count=320):
    dates=[(date(2025,1,1)+timedelta(days=i)).isoformat() for i in range(count)]
    prices=[{"date":d,"close":100+i*.1,"volume":1000} for i,d in enumerate(dates)]
    market=[{"date":d,"price":100+i*.05} for i,d in enumerate(dates)]
    flows=[{"date":d,"net":math.sin(i)} for i,d in enumerate(dates)]
    return prices,flows,market


class DossierTests(unittest.TestCase):
    def test_cost_applies_both_sides_and_empty_is_not_zero(self):
        self.assertAlmostEqual(net_return(.1,10),1.1*.999/1.001-1)
        self.assertIsNone(summarize([])["mean"])
        self.assertIsNone(summarize([])["ci95"])

    def test_analog_maturity_cooldown_and_exact_dates(self):
        prices,flows,market=fixture()
        result=historical_analogs(prices,flows,market)
        self.assertGreater(result["sample"],0)
        calendar=[r["date"] for r in market]
        last=-100
        for match in result["matches"]:
            i=calendar.index(match["event_date"])
            self.assertGreater(i-last,21)
            self.assertEqual(match["entry_date"],calendar[i+1])
            self.assertEqual(match["exit_date"],calendar[i+21])
            self.assertLess(match["exit_date"],calendar[-1])
            self.assertAlmostEqual(match["stock_return"],prices[i+21]["close"]/prices[i+1]["close"]-1)
            last=i

    def test_analog_future_outcomes_do_not_choose_features(self):
        prices,flows,market=fixture()
        result=historical_analogs(prices,flows,market)
        i=[r["date"] for r in market].index(result["matches"][0]["event_date"])
        prices[i+1]["volume"]=0
        changed=historical_analogs(prices,flows,market)
        self.assertEqual(changed["current"],result["current"])
        self.assertNotIn(result["matches"][0]["event_date"],[r["event_date"] for r in changed["matches"]])
        self.assertEqual([r["event_date"] for r in changed["matches"]],[r["event_date"] for r in result["matches"]][1:])

    def test_walk_forward_prior_count_uses_exit_not_signal(self):
        events=[{"event_date":"2025-03-25","entry_date":"2025-03-26","outcomes":{"20":{"exit_date":"2025-04-25","stock_return":.1,"market_return":.02}}},
                {"event_date":"2025-04-28","entry_date":"2025-04-29","outcomes":{"20":{"exit_date":"2025-05-29","stock_return":-.1,"market_return":-.02}}},
                {"event_date":"2025-08-01","entry_date":"2025-08-02","outcomes":{}}]
        result=walk_forward(events,25)
        self.assertEqual(result["sample"],2)
        self.assertEqual(result["periods"][1]["prior_mature_sample"],0)
        self.assertAlmostEqual(result["events"][0]["market_return"],net_return(.02,25))

    def test_disclosure_entry_is_after_release_no_fake_immature_return(self):
        prices,flows,market=fixture()
        day=market[-10]["date"]
        r=disclosure_outcomes([{"timestamp":day+'T23:59:00',"title":"Publication"}],prices,market)[0]
        self.assertEqual(r["entry_date"],market[-9]["date"])
        self.assertIn('5',r['outcomes'])
        self.assertNotIn('20',r['outcomes'])

    def test_constant_flow_has_no_analog(self):
        p,f,m=fixture()
        for row in f: row['net']=1
        self.assertEqual(historical_analogs(p,f,m)['sample'],0)

if __name__=='__main__': unittest.main()
