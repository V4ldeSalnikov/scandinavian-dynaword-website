import json
from pathlib import Path
import unittest
from scripts.build_corpus_catalog import quality_counts, source_domains, annotation_distributions

class CorpusCatalogTests(unittest.TestCase):
    def test_unreported_quality_is_not_zero_quality(self):
        self.assertIsNone(quality_counts({'number_of_samples':3,'annotations':None}))
        self.assertIsNone(quality_counts({'number_of_samples':3,'annotations':{'number_of_annotated_documents':3}}))
        self.assertEqual(quality_counts({'number_of_samples':3,'annotations':{'property_level_counts':{'content_quality':{'good':2}}}}),{'good':2})
        with self.assertRaisesRegex(ValueError,'Invalid published'):
            quality_counts({'number_of_samples':1,'annotations':{'property_level_counts':{'content_quality':{'good':2}}}})

    def test_source_cannot_belong_to_multiple_domains(self):
        with self.assertRaisesRegex(ValueError,'multiple domain'):
            source_domains('<!-- START-DOMAIN TABLE -->\n| Books | [a](url) | 1 |\n| News | [a](url) | 1 |\n<!-- END-DOMAIN TABLE -->')

    def test_checked_in_catalog_keeps_exact_counts_and_pinned_provenance(self):
        catalog=json.loads((Path(__file__).resolve().parents[1]/'web/public/data/corpora.json').read_text())
        self.assertEqual(len(catalog['datasets']),5)
        for corpus in catalog['datasets']:
            self.assertRegex(corpus['revision'],r'^[0-9a-f]{40}$')
            for key in ['records','tokens']:
                self.assertEqual(sum(s[key] for s in corpus['sources']),corpus[key])
                self.assertEqual(sum(d[key] for d in corpus['domains']),corpus[key])
            for source in corpus['sources']:
                self.assertIn(corpus['revision'],source['url'])
                if source['quality'] is not None:
                    self.assertLessEqual(sum(source['quality'].values()),source['records'])

    def test_all_annotation_distributions_match_source_sums(self):
        catalog=json.loads((Path(__file__).resolve().parents[1]/'web/public/data/corpora.json').read_text())
        for corpus in catalog['datasets']:
            for field,expected in (corpus['annotation_distributions'] or {}).items():
                totals={}
                for source in corpus['sources']:
                    for value,n in (source['annotation_distributions'] or {}).get(field,{}).items():totals[value]=totals.get(value,0)+n
                self.assertEqual(totals,expected,(corpus['id'],field))
        with self.assertRaises(ValueError):
            annotation_distributions({'number_of_samples':1,'annotations':{'property_level_counts':{'educational_value':{'high':2}}}})
