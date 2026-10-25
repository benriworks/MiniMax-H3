import unittest
from server import validate, workbook_rows
class ValidationTests(unittest.TestCase):
    def setUp(self): self.row=dict(id='DEMO-001',customer='デモ顧客A',name='架空展示会LP',due='2026-11-10',amount='120000')
    def test_valid(self): self.assertEqual(validate(self.row,[])['amount'],120000)
    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError,'重複'): validate(self.row,[self.row])
    def test_duplicate_case_insensitive(self):
        other=dict(self.row,id='demo-001')
        with self.assertRaisesRegex(ValueError,'重複'): validate(self.row,[other])
    def test_invalid_date(self):
        for value in ['2026-02-30','2026-13-01','2026-11-31','2026-2-03','hello','']:
            with self.subTest(value=value),self.assertRaises(ValueError): validate(dict(self.row,due=value),[])
    def test_negative_and_noninteger_amount(self):
        for value in ['-1','1.5','NaN','Infinity','','100円','1e3']:
            with self.subTest(value=value),self.assertRaises(ValueError): validate(dict(self.row,amount=value),[])
    def test_zero_valid(self): self.assertEqual(validate(dict(self.row,amount='0'),[])['amount'],0)
    def test_workbook(self):
        d=workbook_rows();self.assertEqual(d['headers'],['案件ID','顧客名','案件名','納期','金額円']);self.assertEqual(d['rows'],[['DEMO-001','デモ顧客A','架空展示会LP','2026-11-10',120000],['DEMO-002','デモ顧客B','架空チラシ','2026-11-12',80000],['DEMO-003','デモ顧客C','架空セミナー申込','2026-11-14',50000]]);self.assertEqual(d['total'],250000)
if __name__=='__main__': unittest.main(verbosity=2)
