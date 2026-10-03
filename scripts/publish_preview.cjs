// Runs on GitHub runner only, after the deployment's healthcheck and artifact upload.
const MARKER = '<!-- pyweb-lab1-helios-preview -->';

function message({url, release, operation, runUrl}) {
  const parsed = new URL(url);
  if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error('Invalid published URL');
  }
  if (!/^[a-z0-9][a-z0-9-]{0,100}$/.test(release)) throw new Error('Invalid release');
  if (!['deploy', 'rollback', 'recover'].includes(operation)) throw new Error('Invalid operation');
  const kind = parsed.pathname.includes('/previews/') ? 'Preview' : 'Сайт';
  return `${MARKER}\n### ${kind} на Helios\n\n` +
    `[Открыть ${kind.toLowerCase()}](${parsed.href})\n\n` +
    `Операция: \`${operation}\`. Релиз: \`${release}\`. ` +
    `Healthcheck: HTTP 200, маркер версии и ресурсы проверены.\n\n` +
    `[Успешный запуск пайплайна](${runUrl})\n\n` +
    'Ссылка относится к этой ветке; следующий деплой или откат может изменить её содержимое.';
}

async function updateComment({github, repo, number, body}) {
  const comments = await github.paginate(github.rest.issues.listComments, {...repo, issue_number: number, per_page: 100});
  const existing = comments.find(c => c.user?.type === 'Bot' && c.body?.startsWith(MARKER));
  if (existing) {
    await github.rest.issues.updateComment({...repo, comment_id: existing.id, body});
  } else {
    await github.rest.issues.createComment({...repo, issue_number: number, body});
  }
}

async function reportDeployment({github, context, core, env}) {
  const sha = env.DEPLOYED_SHA;
  if (!/^[a-f0-9]{40}$/.test(sha || '')) throw new Error('Expected immutable deployed commit SHA');
  const repo = context.repo;
  const fullName = `${repo.owner}/${repo.repo}`;
  const runUrl = `${context.serverUrl || 'https://github.com'}/${fullName}/actions/runs/${context.runId}`;
  const body = message({url: env.PUBLISHED_URL, release: env.RELEASE_ID, operation: env.OPERATION || 'deploy', runUrl});
  await core.summary.addRaw(body).write();
  const prs = await github.paginate(github.rest.repos.listPullRequestsAssociatedWithCommit, {...repo, commit_sha: sha, per_page: 100});
  for (const pr of prs) {
    // Do not advertise an old run for a newer head or post to an untrusted fork.
    if (pr.state !== 'open' || pr.head.sha !== sha || pr.head.repo?.full_name !== fullName) continue;
    const current = (await github.rest.pulls.get({...repo, pull_number: pr.number})).data;
    if (current.state !== 'open' || current.head.sha !== sha || current.head.repo?.full_name !== fullName) continue;
    await updateComment({github, repo, number: pr.number, body});
  }
}

module.exports = {MARKER, message, updateComment, reportDeployment};
