// GitHub runner only. Reuse push CI, never accept another branch/SHA or a skipped build.
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function assertTarget({github, context, sha, branch, pullNumber, merged}) {
  const pr = (await github.rest.pulls.get({...context.repo, pull_number: pullNumber})).data;
  if (merged) {
    if (!pr.merged || pr.base.ref !== 'main' || branch !== 'main' || pr.merge_commit_sha !== sha) {
      throw new Error('Expected the exact commit of a pull request merged into main');
    }
  } else if (pr.state !== 'open' || pr.head.sha !== sha || pr.head.ref !== branch ||
             pr.head.repo?.full_name !== `${context.repo.owner}/${context.repo.repo}` || branch === 'main') {
    throw new Error('Preview target is closed, outdated or not a trusted non-main branch');
  }
  const current = (await github.rest.repos.getBranch({...context.repo, branch})).data;
  if (current.commit.sha !== sha) throw new Error('Branch advanced; refusing an outdated deployment');
}

async function waitForCI({github, context, core, env, sleep = delay, now = Date.now,
                          timeoutMs = 30 * 60 * 1000, pollMs = 20000}) {
  const sha = env.EXPECTED_SHA;
  const branch = env.TARGET_BRANCH;
  const pullNumber = Number(env.PULL_NUMBER);
  if (!/^[a-f0-9]{40}$/.test(sha || '') || !branch ||
      !Number.isSafeInteger(pullNumber) || pullNumber < 1 ||
      !['true', 'false'].includes(env.REQUIRE_MERGED)) {
    throw new Error('Expected a commit SHA, branch, PR number and merge mode');
  }
  const target = {github, context, sha, branch, pullNumber, merged: env.REQUIRE_MERGED === 'true'};
  const deadline = now() + timeoutMs;
  let previous;
  while (now() < deadline) {
    await assertTarget(target);
    const response = await github.rest.actions.listWorkflowRuns({
      ...context.repo, workflow_id: 'ci.yml', event: 'push', branch, head_sha: sha, per_page: 100,
    });
    // Do not filter by success: a newer failed/pending run supersedes an older successful one.
    const run = response.data.workflow_runs
      .filter(r => r.event === 'push' && r.head_sha === sha && r.head_branch === branch)
      .sort((a, b) => b.id - a.id)[0];
    const progress = run ? `${run.id}/${run.run_attempt}: ${run.status}/${run.conclusion}` : 'push CI not registered yet';
    if (progress !== previous) { core.info(`Waiting for ${sha}: ${progress}`); previous = progress; }
    if (run?.status === 'completed') {
      if (run.conclusion !== 'success') {
        throw new Error(`Push CI did not succeed (${run.conclusion}): ${run.html_url}`);
      }
      const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
        ...context.repo, run_id: run.id, filter: 'latest', per_page: 100,
      });
      const build = jobs.find(job => job.name === 'CI / build');
      if (!build || build.status !== 'completed' || build.conclusion !== 'success') {
        throw new Error('CI / build must be completed successfully; missing/skipped checks are not accepted');
      }
      await assertTarget(target);
      core.info(`CI / build succeeded: ${run.html_url}`);
      return run.id;
    }
    await sleep(Math.min(pollMs, Math.max(0, deadline - now())));
  }
  throw new Error(`Timed out waiting for successful push CI / build of ${sha}; deployment forbidden`);
}

module.exports = {assertTarget, waitForCI};
