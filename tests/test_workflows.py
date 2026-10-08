import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / '.github/workflows' / name).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)


class WorkflowTests(unittest.TestCase):
    def test_no_workflow_runs_on_push_and_old_ci_waiting_files_are_removed(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            configured = workflow(path.name)
            self.assertNotIn('push', configured['on'], path.name)
            self.assertNotIn('pull_request_target', configured['on'], path.name)
            self.assertNotIn('Wait for CI', str(configured))
        for file in ('.github/workflows/ci.yml', '.github/workflows/ci-gate.yml',
                     'scripts/wait_for_ci.cjs', 'tests/test_ci_gate.cjs'):
            self.assertFalse((ROOT / file).exists(), file)

    def test_pr_preview_runs_full_ci_before_deploy_for_same_head_commit(self):
        preview = workflow('preview.yml')
        self.assertNotIn('branches', preview['on']['pull_request'])
        self.assertEqual(preview['on']['pull_request']['types'], ['opened', 'reopened', 'synchronize'])
        self.assertNotIn('push', preview['on'])
        jobs = preview['jobs']
        self.assertIn('head.repo.full_name == github.repository', jobs['ci']['if'])
        self.assertIn("head.ref != 'main'", jobs['ci']['if'])
        self.assertEqual(jobs['ci']['name'], 'CI')
        self.assertEqual(jobs['ci']['uses'], './.github/workflows/ci-build.yml')
        self.assertEqual(set(jobs['ci']['with']), {'ref'})
        self.assertEqual(jobs['deploy']['needs'], 'ci')
        self.assertNotIn('if', jobs['deploy'])  # Default success(), never always().
        self.assertEqual(jobs['deploy']['with']['ref'], jobs['ci']['with']['ref'])
        self.assertEqual(jobs['ci']['with']['ref'], '${{ github.event.pull_request.head.sha }}')
        self.assertEqual(jobs['deploy']['with']['target_branch'], '${{ github.event.pull_request.head.ref }}')

    def test_merge_production_runs_full_ci_in_main_context_before_both_deployments(self):
        production = workflow('production.yml')
        self.assertEqual(production['on'], {'repository_dispatch': {'types': ['main-merged']}})
        jobs = production['jobs']
        self.assertEqual(jobs['ci']['name'], 'CI')
        self.assertEqual(jobs['ci']['uses'], './.github/workflows/ci-build.yml')
        self.assertEqual(jobs['ci']['with']['require_merged_main'], 'true')
        self.assertEqual(jobs['ci']['with']['merge_pr_number'], '${{ github.event.client_payload.pull_number }}')
        self.assertEqual(jobs['ci']['with']['ref'], '${{ github.event.client_payload.sha }}')
        for job in ('helios', 'pages'):
            self.assertEqual(jobs[job]['needs'], 'ci')
            self.assertNotIn('if', jobs[job])
            self.assertEqual(jobs[job]['with']['ref'], jobs['ci']['with']['ref'])
        self.assertEqual(jobs['helios']['with']['target_branch'], 'main')

    def test_merge_dispatcher_is_metadata_only_and_requires_actual_merge(self):
        merge = workflow('merge.yml')
        self.assertEqual(merge['on'], {'pull_request': {'branches': ['main'], 'types': ['closed']}})
        job = merge['jobs']['dispatch']
        self.assertEqual(job['if'], 'github.event.pull_request.merged == true')
        self.assertEqual(len(job['steps']), 1)
        self.assertNotIn('actions/checkout', str(job))
        self.assertNotIn('environment', job)
        self.assertNotIn('secrets.', str(job))
        self.assertEqual(merge['permissions']['contents'], 'write')
        script = job['steps'][0]['with']['script']
        self.assertIn('createDispatchEvent', script)
        self.assertIn("event_type: 'main-merged'", script)

    def test_production_target_verified_using_metadata_before_checkout(self):
        ci = workflow('ci-build.yml')
        self.assertTrue(all(p == 'read' for p in ci['permissions'].values()))
        self.assertEqual(ci['on']['workflow_call']['inputs']['require_merged_main']['default'], 'false')
        steps = ci['jobs']['build']['steps']
        validation = steps[0]
        self.assertEqual(validation['if'], 'inputs.require_merged_main')
        self.assertIn("WORKFLOW_REF !== 'refs/heads/main'", validation['with']['script'])
        self.assertIn('pr.merge_commit_sha !== sha', validation['with']['script'])
        self.assertTrue(steps[1]['uses'].startswith('actions/checkout@'))
        self.assertEqual(steps[1]['with']['ref'], '${{ inputs.ref }}')

    def test_full_ci_checks_include_production_regressions_and_pinned_checkout(self):
        build = workflow('ci-build.yml')['jobs']['build']
        checkout = next(s for s in build['steps'] if s.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['ref'], '${{ inputs.ref }}')
        self.assertIn('tests/test_production.cjs', str(build['steps']))

    def test_required_checks_match_unique_reusable_job_names_and_include_admins(self):
        ci = workflow('preview.yml')
        protection = json.loads((ROOT / '.github/branch-protection.json').read_text())
        required = {c['context'] for c in protection['required_status_checks']['checks']}
        names = {ci['jobs']['ci']['name'] + ' / build', ci['jobs']['result']['name']}
        self.assertEqual(required, names)
        self.assertEqual(required, {'CI / build', 'Preview ready'})
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
        manual = workflow('helios-manual.yml')
        self.assertEqual(set(manual['on']), {'workflow_dispatch'})
        action = manual['on']['workflow_dispatch']['inputs']['action']
        self.assertEqual(action['options'], ['rollback', 'recover'])
        self.assertEqual(action['default'], 'rollback')
        jobs = manual['jobs']
        resolve_step = jobs['resolve']['steps'][0]
        self.assertEqual(resolve_step['env']['OPERATION'], '${{ inputs.action }}')
        self.assertIn("['rollback', 'recover'].includes(process.env.OPERATION)", resolve_step['with']['script'])
        self.assertEqual(jobs['build']['needs'], 'resolve')
        self.assertEqual(jobs['build']['with']['ref'], '${{ needs.resolve.outputs.ref }}')
        publish = jobs['publish']
        self.assertEqual(set(publish['needs']), {'resolve', 'build'})
        self.assertNotIn('if', publish)  # Only success() allows publication.
        self.assertEqual(publish['uses'], './.github/workflows/helios.yml')
        self.assertEqual(publish['with']['ref'], jobs['build']['with']['ref'])
        self.assertEqual(publish['with']['target_branch'], '${{ needs.resolve.outputs.branch }}')
        self.assertEqual(publish['with']['automatic'], 'false')
        self.assertEqual(publish['secrets'], 'inherit')

    def test_reusable_helios_contains_only_publication_no_skipped_manual_jobs(self):
        helios = workflow('helios.yml')
        self.assertEqual(set(helios['on']), {'workflow_call'})
        self.assertEqual(set(helios['jobs']), {'deploy'})
        deploy = helios['jobs']['deploy']
        self.assertNotIn('needs', deploy)
        self.assertNotIn('if', deploy)
        self.assertNotIn('needs.resolve', str(helios))
        checkout = next(s for s in deploy['steps'] if s.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['ref'], '${{ inputs.ref }}')
        self.assertEqual(helios['on']['workflow_call']['inputs']['automatic']['default'], 'true')
        for file, job in [('preview.yml', 'deploy'), ('production.yml', 'helios')]:
            caller = workflow(file)['jobs'][job]
            self.assertEqual(caller['uses'], './.github/workflows/helios.yml')
            self.assertEqual(caller['needs'], 'ci')
            self.assertNotIn('automatic', caller['with'])

    def test_pages_only_automatically_called_after_production_ci_without_manual_jobs(self):
        pages = workflow('pages.yml')
        self.assertEqual(set(pages['on']), {'workflow_call'})
        jobs = pages['jobs']
        self.assertEqual(set(jobs), {'build', 'deploy'})
        caller = workflow('production.yml')['jobs']['pages']
        self.assertEqual(caller['uses'], './.github/workflows/pages.yml')
        self.assertEqual(caller['needs'], 'ci')
        self.assertNotIn('if', caller)
        self.assertNotIn('needs.resolve', str(pages))
        self.assertEqual(jobs['deploy']['needs'], 'build')
        self.assertNotIn('if', jobs['deploy'])
        for job, ref in [('build', '${{ inputs.ref }}'),
                         ('deploy', '${{ needs.build.outputs.ref }}')]:
            checkout = next(s for s in jobs[job]['steps'] if s.get('uses', '').startswith('actions/checkout@'))
            self.assertEqual(checkout['with']['ref'], ref)

    def test_pages_requires_main_context_and_preserves_oidc_and_environment(self):
        jobs = workflow('pages.yml')['jobs']
        guard = jobs['build']['steps'][0]
        self.assertEqual(guard['env']['WORKFLOW_REF'], '${{ github.ref }}')
        self.assertIn('"$WORKFLOW_REF" != "refs/heads/main"', guard['run'])
        self.assertIn('exit 1', guard['run'])
        self.assertEqual(jobs['deploy']['environment']['name'], 'github-pages')
        self.assertEqual(jobs['deploy']['permissions']['pages'], 'write')
        self.assertEqual(jobs['deploy']['permissions']['id-token'], 'write')
        uses = [s.get('uses', '') for s in jobs['deploy']['steps']]
        self.assertTrue(any(u.startswith('actions/deploy-pages@') for u in uses))

    def test_disabled_deploy_fails_instead_of_skipping_required_check(self):
        deploy = workflow('helios.yml')['jobs']['deploy']
        self.assertNotIn('if', deploy)
        step = next(s for s in deploy['steps'] if s.get('env', {}).get('HELIOS_ENABLED'))
        self.assertEqual(step['if'], 'inputs.automatic')
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
        self.assertNotIn('concurrency', workflow('helios-manual.yml'))


if __name__ == '__main__':
    unittest.main()
