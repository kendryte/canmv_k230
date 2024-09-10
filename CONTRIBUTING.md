# How to Contribute to this Project

## 1. Clone the Manifest Repository

This open-source project consists of multiple sub-repositories managed by Google’s git-repo tool. The core configuration repository is the Manifest repository, which contains information about all the sub-repositories (usually in .repo/manifest.xml). Developers need to initialize and sync the Manifest repository locally to fetch all the sub-repositories:  

本开源项目包括多个子库，使用Google git-repo 工具管理，它的核心配置仓库是包含所有子库信息的 Manifest 仓库（通常是 .repo/manifest.xml）。开发者需要在本地初始化并同步该 Manifest 仓库，以获取所有的子库：

```bash
repo init -u https://github.com/canmv-k230/manifest.git -b master --repo-url=https://github.com/canmv-k230/git-repo.git
repo sync
```

## 2. Create your local feature branch

After `repo sync`, the repo tool will not create a branch for the local codebase. Run the following command to create a new feature branch across all related sub-repositories for development.

`repo sync` 完成后, repo 工具不会为本地代码库创建分支。请执行以下命令，在所有相关子库中创建一个新的特性分支，用于进行开发。

```bash
repo start feature/new-feature-name --all
```

## 3. Start your feature development

Depending on the feature being developed, your changes may involve multiple sub-repositories. Enter the relevant sub-repositories to make your changes and commit them. Ensure each commit message is clear and accurately describes the changes.

根据不同的功能开发需要，您的改动可能同时涉及不同的子代码库。请进入相关的子库开发并提交更改。提交时要确保每个子库的提交信息清晰且描述准确。


```bash
git add .
git commit -m "描述性的提交信息"
```

## 4. Push commits to your own forked sub-repo

After completing the feature development, for the sub-repositories that have changes, developers should first fork these repositories under their own account. Then, add the remote URL of the forked repository for these sub-repositories and push the changes to the corresponding branch. For example:

在功能开发完成后，对于有改动的子库，开发者先 fork 这些库到自己名下。然后为这些子库添加远程 Fork 仓库的 URL，再将更改推送到相应的分支。例如：

```bash
git remote add fork git@github.com:your-username/submodule-repo.git
git push fork feature/new-feature-name:dev
```

## 5.  Create a Pull Request for each sub-repo

On the GitHub page of each sub-repository, create a Pull Request (PR) targeting the appropriate branch of the main Manifest repository. The PR description should detail the changes made in the sub-repositories.

在每个子库的 GitHub 页面上，创建一个 PR，指向主 Manifest 仓库的目标分支。PR 描述中应详细说明涉及的子库更改。
