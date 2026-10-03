import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / '.github/workflows' / name).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)


class WorkflowTests(unittest.TestCase):
    def test_one_ci_event_for_each_push_not_duplicate_pull_request(self):
        ci = workflow('ci.yml')
        self.assertIn('push', ci['on'])
        self.assertNotIn('pull_request', ci['on'])
        self.assertNotIn('pull_request_target', ci['on'])
        self.assertNotIn('push', workflow('helios.yml')['on'])

    def test_helios_call_requires_ci_success_and_exact_same_sha(self):
        ci = workflow('ci.yml')
        self.assertEqual(ci['jobs']['deploy']['needs'], 'build')
        self.assertNotIn('if', ci['jobs']['deploy'])  # Default success(), never always().
        self.assertEqual(ci['jobs']['deploy']['with']['ref'], ci['jobs']['build']['with']['ref'])
        build = workflow('ci-build.yml')['jobs']['build']
        checkout = next(s for s in build['steps'] if s.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['ref'], '${{ inputs.ref }}')

    def test_required_checks_match_unique_reusable_job_names_and_include_admins(self):
        ci = workflow('ci.yml')
        protection = json.loads((ROOT / '.github/branch-protection.json').read_text())
        required = {c['context'] for c in protection['required_status_checks']['checks']}
        names = {ci['jobs']['build']['name'] + ' / build', ci['jobs']['deploy']['name'] + ' / deploy'}
        self.assertEqual(required, names)
        self.assertTrue(protection['required_status_checks']['strict'])
        self.assertTrue(protection['enforce_admins'])
        self.assertTrue(all(c['app_id'] == 15368 for c in protection['required_status_checks']['checks']))

    def test_manual_operations_have_ci_gate_with_immutable_target(self):
        jobs = workflow('helios.yml')['jobs']
        self.assertEqual(jobs['build']['needs'], 'resolve')
        self.assertEqual(jobs['build']['with']['ref'], '${{ needs.resolve.outputs.ref }}')
        self.assertIn('build', jobs['deploy']['needs'])
        self.assertIn("needs.build.result == 'success'", jobs['deploy']['if'])
        self.assertEqual(jobs['resolve']['if'], '${{ !inputs.ref }}')
        self.assertEqual(jobs['build']['if'], '${{ !inputs.ref }}')

    def test_disabled_deploy_fails_instead_of_skipping_required_check(self):
        deploy = workflow('helios.yml')['jobs']['deploy']
        self.assertNotIn('HELIOS_ENABLED', deploy['if'])
        step = next(s for s in deploy['steps'] if s.get('env', {}).get('HELIOS_ENABLED'))
        self.assertIn('exit 1', step['run'])

    def test_preview_report_is_last_and_not_always_after_failure(self):
        deploy = workflow('helios.yml')['jobs']['deploy']
        self.assertEqual(deploy['environment']['url'], '${{ steps.config.outputs.site_url }}')
        report = deploy['steps'][-1]
        self.assertIn('publish_preview.cjs', report['with']['script'])
        self.assertNotIn('if', report)
        self.assertEqual(deploy['permissions']['pull-requests'], 'write')

    def test_pr_opened_notification_never_rebuilds_or_executes_pr_code(self):
        link = workflow('preview-link.yml')
        self.assertEqual(link['on']['pull_request']['types'], ['opened', 'reopened'])
        self.assertNotIn('pull_request_target', link['on'])
        job = link['jobs']['link']
        self.assertIn('github.repository', job['if'])
        self.assertEqual(len(job['steps']), 1)
        self.assertTrue(job['steps'][0]['uses'].startswith('actions/github-script@'))
        self.assertNotIn('actions/checkout', str(job))
        self.assertNotIn('secrets.', str(job))

    def test_global_deployment_queue_is_not_cancelled_mid_upload(self):
        concurrency = workflow('helios.yml')['concurrency']
        self.assertEqual(concurrency['queue'], 'max')
        self.assertEqual(concurrency['cancel-in-progress'], 'false')


if __name__ == '__main__':
    unittest.main()
