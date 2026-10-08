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
        self.assertEqual(ci['on']['push']['branches'], ['**'])
        self.assertEqual(set(ci['jobs']), {'build'})
        self.assertNotIn('push', workflow('helios.yml')['on'])
        self.assertNotIn('push', workflow('pages.yml')['on'])

    def test_pr_preview_waits_for_same_head_push_ci_without_rebuilding(self):
        preview = workflow('preview.yml')
        self.assertNotIn('branches', preview['on']['pull_request'])
        self.assertEqual(preview['on']['pull_request']['types'], ['opened', 'reopened', 'synchronize'])
        self.assertNotIn('push', preview['on'])
        jobs = preview['jobs']
        self.assertIn('head.repo.full_name == github.repository', jobs['ci']['if'])
        self.assertIn("head.ref != 'main'", jobs['ci']['if'])
        self.assertEqual(jobs['ci']['uses'], './.github/workflows/ci-gate.yml')
        self.assertEqual(jobs['deploy']['needs'], 'ci')
        self.assertNotIn('if', jobs['deploy'])  # Default success(), never always().
        self.assertEqual(jobs['deploy']['with']['ref'], jobs['ci']['with']['ref'])
        self.assertEqual(jobs['ci']['with']['ref'], '${{ github.event.pull_request.head.sha }}')
        self.assertEqual(jobs['deploy']['with']['target_branch'], jobs['ci']['with']['branch'])

    def test_merge_production_has_one_shared_gate_for_both_deployments(self):
        production = workflow('production.yml')
        self.assertEqual(production['on']['pull_request'], {'branches': ['main'], 'types': ['closed']})
        jobs = production['jobs']
        self.assertEqual(jobs['ci']['if'], 'github.event.pull_request.merged == true')
        self.assertEqual(jobs['ci']['uses'], './.github/workflows/ci-gate.yml')
        self.assertEqual(jobs['ci']['with']['merged'], 'true')
        self.assertEqual(jobs['ci']['with']['branch'], 'main')
        self.assertEqual(jobs['ci']['with']['ref'], '${{ github.event.pull_request.merge_commit_sha }}')
        for job in ('helios', 'pages'):
            self.assertEqual(jobs[job]['needs'], 'ci')
            self.assertNotIn('if', jobs[job])
            self.assertEqual(jobs[job]['with']['ref'], jobs['ci']['with']['ref'])
        self.assertEqual(jobs['helios']['with']['target_branch'], 'main')

    def test_ci_gate_uses_read_only_permissions_and_exact_target_checkout(self):
        gate = workflow('ci-gate.yml')
        self.assertEqual(set(gate['on']), {'workflow_call'})
        self.assertTrue(all(p == 'read' for p in gate['permissions'].values()))
        self.assertEqual(gate['permissions']['actions'], 'read')
        steps = gate['jobs']['wait']['steps']
        self.assertEqual(steps[0]['with']['ref'], '${{ inputs.ref }}')
        self.assertIn('wait_for_ci.cjs', steps[-1]['with']['script'])
        self.assertNotIn('ci-build.yml', str(gate))

    def test_full_ci_checks_include_the_new_gate_regressions_and_pinned_checkout(self):
        build = workflow('ci-build.yml')['jobs']['build']
        checkout = next(s for s in build['steps'] if s.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['ref'], '${{ inputs.ref }}')
        self.assertIn('tests/test_ci_gate.cjs', str(build['steps']))

    def test_required_checks_match_unique_reusable_job_names_and_include_admins(self):
        ci = workflow('ci.yml')
        protection = json.loads((ROOT / '.github/branch-protection.json').read_text())
        required = {c['context'] for c in protection['required_status_checks']['checks']}
        names = {ci['jobs']['build']['name'] + ' / build', workflow('preview.yml')['jobs']['result']['name']}
        self.assertEqual(required, names)
        self.assertTrue(protection['required_status_checks']['strict'])
        self.assertTrue(protection['enforce_admins'])
        self.assertTrue(all(c['app_id'] == 15368 for c in protection['required_status_checks']['checks']))

    def test_required_preview_result_rejects_skipped_failed_and_cancelled_dependencies(self):
        jobs = workflow('preview.yml')['jobs']
        result = jobs['result']
        self.assertEqual(result['if'], 'always()')
        self.assertEqual(set(result['needs']), {'ci', 'deploy'})
        step = result['steps'][0]
        self.assertEqual(step['env']['CI_RESULT'], '${{ needs.ci.result }}')
        self.assertEqual(step['env']['DEPLOY_RESULT'], '${{ needs.deploy.result }}')
        self.assertIn('"$CI_RESULT" != "success"', step['run'])
        self.assertIn('"$DEPLOY_RESULT" != "success"', step['run'])
        self.assertIn('exit 1', step['run'])

    def test_manual_operations_have_ci_gate_with_immutable_target(self):
        jobs = workflow('helios.yml')['jobs']
        self.assertEqual(jobs['build']['needs'], 'resolve')
        self.assertEqual(jobs['build']['with']['ref'], '${{ needs.resolve.outputs.ref }}')
        self.assertIn('build', jobs['deploy']['needs'])
        self.assertIn("needs.build.result == 'success'", jobs['deploy']['if'])
        self.assertEqual(jobs['resolve']['if'], '${{ !inputs.ref }}')
        self.assertEqual(jobs['build']['if'], '${{ !inputs.ref }}')

    def test_manual_pages_performs_full_ci_before_build_and_deploy(self):
        jobs = workflow('pages.yml')['jobs']
        self.assertEqual(jobs['ci']['uses'], './.github/workflows/ci-build.yml')
        self.assertEqual(jobs['ci']['needs'], 'resolve')
        self.assertEqual(jobs['ci']['with']['ref'], '${{ needs.resolve.outputs.ref }}')
        self.assertIn('ci', jobs['build']['needs'])
        self.assertIn("needs.ci.result == 'success'", jobs['build']['if'])
        self.assertEqual(jobs['ci']['if'], '${{ !inputs.ref }}')
        self.assertEqual(jobs['deploy']['needs'], 'build')
        self.assertNotIn('if', jobs['deploy'])
        for job, ref in [('build', '${{ inputs.ref || needs.resolve.outputs.ref }}'),
                         ('deploy', '${{ needs.build.outputs.ref }}')]:
            checkout = next(s for s in jobs[job]['steps'] if s.get('uses', '').startswith('actions/checkout@'))
            self.assertEqual(checkout['with']['ref'], ref)

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

    def test_obsolete_link_only_workflow_removed(self):
        self.assertFalse((ROOT / '.github/workflows/preview-link.yml').exists())

    def test_global_deployment_queue_is_not_cancelled_mid_upload(self):
        concurrency = workflow('helios.yml')['concurrency']
        self.assertEqual(concurrency['queue'], 'max')
        self.assertEqual(concurrency['cancel-in-progress'], 'false')


if __name__ == '__main__':
    unittest.main()
