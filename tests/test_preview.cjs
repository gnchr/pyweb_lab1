const assert = require('node:assert/strict');
const test = require('node:test');
const {MARKER, message, reportDeployment} = require('../scripts/publish_preview.cjs');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

// Execute the metadata-only workflow's inline script as github-script does.
const workflowText = fs.readFileSync(path.join(__dirname, '../.github/workflows/preview-link.yml'), 'utf8');
const inline = workflowText.split('          script: |')[1].replace(/^\r?\n/, '').split(/\r?\n/).map(l => l.replace(/^ {12}/, '')).join('\n');
const ExistingReporter = new Function('github', 'context', 'require', 'process', `return (async () => {${inline}})();`);

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

function openedFixture(statuses, existingComments = []) {
  const args = fixture();
  const branch = 'feature/a';
  args.context.payload = {pull_request: {...pr, head: {...pr.head, ref: branch}}, repository: {default_branch: 'main'}};
  args.github.rest.repos.listDeployments = 'deployments';
  args.github.rest.repos.listDeploymentStatuses = 'statuses';
  args.github.paginate = async (method, params) => {
    if (method === 'deployments') { assert.equal(params.sha, sha); return [{id: 99}]; }
    if (method === 'statuses') return statuses;
    return existingComments;
  };
  const hash = crypto.createHash('sha256').update(branch).digest('hex').slice(0, 12);
  args.expected = `https://example.org/pyweb_lab1/previews/feature-a-${hash}/`;
  args.process = {env: {BASE_SITE_URL: 'https://example.org/pyweb_lab1/'}};
  return args;
}
test('opening PR after deploy still gets a link without a new build', async () => {
  const args = openedFixture([]);
  args.github.paginate = async method => method === 'deployments' ? [{id: 99}] : method === 'statuses' ? [{state: 'success', environment_url: args.expected}] : [];
  await ExistingReporter(args.github, args.context, require, args.process);
  assert.equal(args.calls[0][0], 'create'); assert.ok(args.calls[0][1].body.includes(args.expected));
});
test('pending deployment or another branch URL does not advertise a preview', async () => {
  for (const status of [{state: 'pending', environment_url: 'https://example.org/'}, {state: 'success', environment_url: 'https://other.org/preview/'}]) {
    const args = openedFixture([status]);
    await ExistingReporter(args.github, args.context, require, args.process);
    assert.equal(args.calls.length, 0);
  }
});
test('PR-opened notification does not duplicate a deployment comment', async () => {
  const args = openedFixture([], [{body: MARKER, user: {type: 'Bot'}}]);
  args.github.paginate = async method => method === 'deployments' ? [{id: 99}] : method === 'statuses' ? [{state: 'success', environment_url: args.expected}] : [{body: MARKER, user: {type: 'Bot'}}];
  await ExistingReporter(args.github, args.context, require, args.process); assert.equal(args.calls.length, 0);
});
