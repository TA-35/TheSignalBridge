# Branch protection for `main`

`main` only changes through a pull request. That way CI checks every change,
the team sees it before it lands, and merging stays the one step that ships
(merging to `main` deploys the frontend and backend).

There are two layers.

## 1. Git hooks in this folder (works now)

- `pre-commit` refuses a commit made straight onto `main`.
- `pre-push` refuses a push to `main`, including a force push or deleting it.

Turn them on once per clone (worktrees of the same clone share the setting):

```sh
git config core.hooksPath .githooks
```

If a hook stops you, your work is safe:

- **Commit refused on `main`:** run `git switch -c <branch-name>`, which keeps
  your changes, and commit on that branch.
- **Push refused:** push your branch (`git push -u origin <branch-name>`) and
  open a pull request.

The hooks run on your own computer, so `git commit --no-verify` or
`git push --no-verify` skips them. They catch mistakes; they aren't a lock.
Merging a pull request on GitHub happens on GitHub and is never blocked by
them, and neither is pulling.

## 2. GitHub ruleset (needs a paid GitHub plan)

[`.github/rulesets/protect-main.json`](../.github/rulesets/protect-main.json)
is the same protection enforced by GitHub, which `--no-verify` can't skip:

- `main` can't be deleted or force-pushed.
- Changes reach `main` only through a pull request (merge, squash or rebase).
  No approving review is required. Set `required_approving_review_count` to 1
  if the team wants every change reviewed.

GitHub only enforces rulesets on a **private** repository with GitHub Pro,
Team or Enterprise
([About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)).
If TA-35 has, or gets, GitHub Team, a repository admin turns it on like this:

1. **Settings → Rules → Rulesets → New ruleset → Import a ruleset**.
2. Choose `protect-main.json` and select **Create**.

Required CI checks are left out on purpose. Each CI workflow only runs when its
own folder changes, and a workflow that doesn't run never reports. If its check
were required, every pull request that doesn't touch that folder would wait for
it forever. Making checks required first needs the CI jobs to report on every
pull request, with distinct names (all three are called `checks` today).
