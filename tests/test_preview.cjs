const assert = require('node:assert/strict');
const test = require('node:test');
const {MARKER, message, reportDeployment} = require('../scripts/publish_preview.cjs');

const sha = 'a'.repeat(40);
const pr = {number: 4, state: 'open', head: {sha, repo: {full_name: 'owner/repo'}}};
function fixture(prs = [pr], comments = [], current = pr) {
  const calls = [];
  const github = {
    rest: {
      repos: {listPullRequestsAssociatedWithCommit: 'prs'},
      issues: {
        listComments: 'comments',
        createComment: async args => calls.push(['create', args]),
        updateComment: async args => calls.push(['update', args]),
      },
      pulls: {get: async () => ({data: current})},
    },
    paginate: async method => method === 'prs' ? prs : comments,
  };
  const core = {summary: {addRaw: value => {calls.push(['summary', value]); return core.summary;}, write: async () => {}}};
  const context = {repo: {owner: 'owner', repo: 'repo'}, runId: 42};
  const env = {DEPLOYED_SHA: sha, PUBLISHED_URL: 'https://example.org/pyweb_lab1/previews/test-abc/', RELEASE_ID: 'release-v1', OPERATION: 'deploy'};
  return {github, core, context, env, calls};
}

test('successful preview gets summary and PR comment with URL and release', async () => {
  const args = fixture(); await reportDeployment(args);
  assert.equal(args.calls[1][0], 'create');
  assert.match(args.calls[1][1].body, /https:\/\/example.org\/pyweb_lab1\/previews\/test-abc\//);
  assert.match(args.calls[1][1].body, /release-v1/);
});
test('existing bot comment is updated instead of duplicated', async () => {
  const args = fixture([pr], [{id: 17, body: MARKER, user: {type: 'Bot'}}]);
  await reportDeployment(args); assert.equal(args.calls[1][0], 'update'); assert.equal(args.calls[1][1].comment_id, 17);
});
test('a user-authored marker does not permit overwriting their comment', async () => {
  const args = fixture([pr], [{id: 17, body: MARKER, user: {type: 'User'}}]);
  await reportDeployment(args); assert.equal(args.calls[1][0], 'create');
});
test('fork, closed and different-SHA pull requests never get a comment', async () => {
  for (const changed of [{state: 'closed'}, {head: {...pr.head, sha: 'b'.repeat(40)}}, {head: {...pr.head, repo: {full_name: 'fork/repo'}}}]) {
    const args = fixture([{...pr, ...changed}]); await reportDeployment(args); assert.equal(args.calls.length, 1);
  }
});
test('head changed while PR lookup ran: do not replace the current comment', async () => {
  const args = fixture([pr], [], {...pr, head: {...pr.head, sha: 'b'.repeat(40)}});
  await reportDeployment(args); assert.equal(args.calls.length, 1);
});
test('a branch without PR still gets the deployment summary', async () => {
  const args = fixture([]); await reportDeployment(args); assert.equal(args.calls[0][0], 'summary');
});
test('invalid URLs, release IDs and operations are rejected', () => {
  for (const change of [{url: 'javascript:alert(1)'}, {release: 'unsafe\nrelease'}, {operation: 'unknown'}]) {
    assert.throws(() => message({url: 'https://example.org/', release: 'v1', operation: 'deploy', runUrl: 'https://github.com/run', ...change}));
  }
});
