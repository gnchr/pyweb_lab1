const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');

// Execute the real metadata-only YAML scripts, without a network or repository checkout.
function script(file) {
  const text = fs.readFileSync(path.join(__dirname, '../.github/workflows', file), 'utf8');
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex(line => /^ {10}script: \|$/.test(line));
  assert.ok(start >= 0, `github-script missing in ${file}`);
  const body = [];
  for (const line of lines.slice(start + 1)) {
    if (line.trim() && !line.startsWith('            ')) break;
    body.push(line.replace(/^ {12}/, ''));
  }
  return new Function('github', 'context', 'core', 'process', `return (async () => {${body.join('\n')}})();`);
}
const dispatch = script('merge.yml');
const validate = script('ci-build.yml');
const sha = 'a'.repeat(40);
const other = 'b'.repeat(40);
function fixture() {
  const calls = [];
  const pr = {merged: true, base: {ref: 'main'}, merge_commit_sha: sha};
  const main = {commit: {sha}};
  const github = {rest: {
    pulls: {get: async params => {calls.push(['pr', params]); return {data: pr};}},
    repos: {
      getBranch: async params => {calls.push(['branch', params]); return {data: main};},
      createDispatchEvent: async params => {calls.push(['dispatch', params]);},
    },
  }};
  const context = {repo: {owner: 'owner', repo: 'repo'}, payload: {pull_request: {number: 7}}};
  const core = {info: () => {}};
  const process = {env: {EXPECTED_SHA: sha, PULL_NUMBER: '7', WORKFLOW_REF: 'refs/heads/main'}};
  return {github, context, core, process, calls, pr, main};
}

test('a merged PR dispatches main-context production with its exact SHA and PR number', async () => {
  const args = fixture(); await dispatch(args.github, args.context, args.core, args.process);
  const posted = args.calls.find(c => c[0] === 'dispatch')[1];
  assert.equal(posted.event_type, 'main-merged');
  assert.deepEqual(posted.client_payload, {sha, pull_number: '7'});
});
test('closing without merge, another base or an invalid SHA never dispatches production', async () => {
  for (const change of [{merged: false}, {base: {ref: 'develop'}}, {merge_commit_sha: 'main'}]) {
    const args = fixture(); Object.assign(args.pr, change);
    await assert.rejects(dispatch(args.github, args.context, args.core, args.process), /actually merged/);
    assert.ok(!args.calls.some(c => c[0] === 'dispatch'));
  }
});
test('an outdated merge cannot dispatch over a newer main', async () => {
  const args = fixture(); args.main.commit.sha = other;
  await assert.rejects(dispatch(args.github, args.context, args.core, args.process), /Main advanced/);
  assert.ok(!args.calls.some(c => c[0] === 'dispatch'));
});
test('production CI accepts only the exact commit already merged into current main', async () => {
  const args = fixture(); await validate(args.github, args.context, args.core, args.process);
  assert.equal(args.calls[0][1].pull_number, 7);
  assert.equal(args.calls[1][1].branch, 'main');
});
test('the rejected refs/pull/7/merge context fails before any checkout or API request', async () => {
  const args = fixture(); args.process.env.WORKFLOW_REF = 'refs/pull/7/merge';
  await assert.rejects(validate(args.github, args.context, args.core, args.process), /main context/);
  assert.equal(args.calls.length, 0);
});
test('other branches, tags and invalid dispatch data cannot run production code', async () => {
  for (const change of [{WORKFLOW_REF: 'refs/heads/feature'}, {WORKFLOW_REF: 'refs/tags/v1'},
                       {EXPECTED_SHA: 'main'}, {PULL_NUMBER: ''}, {PULL_NUMBER: '0'}, {PULL_NUMBER: 'NaN'}]) {
    const args = fixture(); Object.assign(args.process.env, change);
    await assert.rejects(validate(args.github, args.context, args.core, args.process), /main context/);
    assert.equal(args.calls.length, 0);
  }
});
test('an unmerged PR, another base or a mismatched SHA is rejected before checkout', async () => {
  for (const change of [{merged: false}, {base: {ref: 'develop'}}, {merge_commit_sha: other}]) {
    const args = fixture(); Object.assign(args.pr, change);
    await assert.rejects(validate(args.github, args.context, args.core, args.process), /actually merged/);
  }
});
test('a main advance after dispatch aborts production before checkout', async () => {
  const args = fixture(); args.main.commit.sha = other;
  await assert.rejects(validate(args.github, args.context, args.core, args.process), /Main advanced/);
});
