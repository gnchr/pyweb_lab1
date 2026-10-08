const assert = require('node:assert/strict');
const test = require('node:test');
const {waitForCI} = require('../scripts/wait_for_ci.cjs');

const sha = 'a'.repeat(40);
const other = 'b'.repeat(40);
function fixture({runs, merged = false, jobs} = {}) {
  let ticks = 0;
  const calls = [];
  const env = {EXPECTED_SHA: sha, TARGET_BRANCH: merged ? 'main' : 'feature/a',
               PULL_NUMBER: '4', REQUIRE_MERGED: String(merged)};
  const pr = {number: 4, state: merged ? 'closed' : 'open', merged,
              base: {ref: 'main'}, merge_commit_sha: merged ? sha : null,
              head: {sha: merged ? other : sha, ref: 'feature/a', repo: {full_name: 'owner/repo'}}};
  const run = {id: 9, run_attempt: 1, head_sha: sha, head_branch: env.TARGET_BRANCH,
               event: 'push', status: 'completed', conclusion: 'success', html_url: 'https://github.com/run/9'};
  const github = {
    rest: {
      pulls: {get: async () => ({data: pr})},
      repos: {getBranch: async () => ({data: {commit: {sha: env.EXPECTED_SHA}}})},
      actions: {
        listWorkflowRuns: async params => {calls.push(params); return {data: {workflow_runs: runs ?? [run]}};},
        listJobsForWorkflowRun: 'jobs',
      },
    },
    paginate: async (method, params) => {
      assert.equal(method, 'jobs'); assert.equal(params.filter, 'latest');
      return jobs ?? [{name: 'CI / build', status: 'completed', conclusion: 'success'}];
    },
  };
  return {github, context: {repo: {owner: 'owner', repo: 'repo'}}, core: {info: () => {}}, env,
          now: () => ticks, sleep: async ms => {ticks += ms;}, timeoutMs: 100, pollMs: 10, calls, pr, run};
}

test('PR opened after completed push CI may deploy immediately, without rebuilding', async () => {
  const args = fixture();
  assert.equal(await waitForCI(args), 9);
  assert.equal(args.calls[0].workflow_id, 'ci.yml');
  assert.equal(args.calls[0].head_sha, sha); assert.equal(args.calls[0].event, 'push');
});

test('PR opened before push CI is registered waits until that exact CI succeeds', async () => {
  const args = fixture(); let requests = 0;
  args.github.rest.actions.listWorkflowRuns = async () => {
    const runs = requests++ === 0 ? [] : [{...args.run, status: requests === 2 ? 'in_progress' : 'completed'}];
    return {data: {workflow_runs: runs}};
  };
  assert.equal(await waitForCI(args), 9); assert.equal(requests, 3);
});

test('failure, cancellation, skipped and neutral push CI always forbid deployment', async () => {
  for (const conclusion of ['failure', 'cancelled', 'skipped', 'neutral', 'timed_out', 'action_required']) {
    const args = fixture(); args.run.conclusion = conclusion;
    await assert.rejects(waitForCI(args), /Push CI did not succeed/);
  }
});

test('no CI and permanently running CI time out without publication', async () => {
  for (const runs of [[], [{...fixture().run, status: 'in_progress', conclusion: null}]]) {
    await assert.rejects(waitForCI(fixture({runs})), /Timed out/);
  }
});

test('another SHA, another branch or manual CI cannot unlock this deployment', async () => {
  for (const change of [{head_sha: other}, {head_branch: 'other'}, {event: 'workflow_dispatch'}]) {
    const run = {...fixture().run, ...change};
    await assert.rejects(waitForCI(fixture({runs: [run]})), /Timed out/);
  }
});

test('newer failed CI wins over an older success', async () => {
  const run = fixture().run;
  await assert.rejects(waitForCI(fixture({runs: [run, {...run, id: 10, conclusion: 'failure'}]})), /did not succeed/);
});

test('newer pending CI wins over an older success', async () => {
  const run = fixture().run;
  await assert.rejects(waitForCI(fixture({runs: [run, {...run, id: 10, status: 'queued', conclusion: null}]})), /Timed out/);
});

test('missing, unfinished or skipped CI / build is never accepted', async () => {
  for (const jobs of [[], [{name: 'other', status: 'completed', conclusion: 'success'}],
                      [{name: 'CI / build', status: 'completed', conclusion: 'skipped'}],
                      [{name: 'CI / build', status: 'in_progress', conclusion: null}]]) {
    await assert.rejects(waitForCI(fixture({jobs})), /CI \/ build must be completed successfully/);
  }
});

test('closed, changed and fork PR heads cannot become preview deployments', async () => {
  for (const change of [{state: 'closed'}, {head: {...fixture().pr.head, sha: other}},
                       {head: {...fixture().pr.head, ref: 'other'}},
                       {head: {...fixture().pr.head, repo: {full_name: 'fork/repo'}}}]) {
    const args = fixture(); Object.assign(args.pr, change);
    await assert.rejects(waitForCI(args), /Preview target/);
    assert.equal(args.calls.length, 0);
  }
});

test('branch advanced while CI was running: outdated publication forbidden', async () => {
  const args = fixture();
  args.github.rest.repos.getBranch = async () => ({data: {commit: {sha: other}}});
  await assert.rejects(waitForCI(args), /Branch advanced/);
});

test('PR head changed between success lookup and final validation: publication forbidden', async () => {
  const args = fixture();
  args.github.paginate = async () => {
    args.pr.head.sha = other;
    return [{name: 'CI / build', status: 'completed', conclusion: 'success'}];
  };
  await assert.rejects(waitForCI(args), /Preview target/);
});

test('production waits for the merge commit CI, not the pre-merge branch CI', async () => {
  const args = fixture({merged: true});
  assert.equal(await waitForCI(args), 9);
  assert.equal(args.calls[0].branch, 'main'); assert.equal(args.calls[0].head_sha, sha);
  assert.notEqual(args.pr.head.sha, args.calls[0].head_sha);
});

test('closing without merge, a different merge SHA or another base cannot deploy production', async () => {
  for (const change of [{merged: false}, {merge_commit_sha: other}, {base: {ref: 'develop'}}]) {
    const args = fixture({merged: true}); Object.assign(args.pr, change);
    await assert.rejects(waitForCI(args), /exact commit/);
  }
});

test('invalid gate inputs fail before making any API requests', async () => {
  for (const change of [{EXPECTED_SHA: 'main'}, {TARGET_BRANCH: ''}, {PULL_NUMBER: '0'},
                       {PULL_NUMBER: 'not-a-number'}, {REQUIRE_MERGED: 'yes'}]) {
    const args = fixture(); Object.assign(args.env, change);
    await assert.rejects(waitForCI(args), /Expected a commit SHA/);
    assert.equal(args.calls.length, 0);
  }
});
