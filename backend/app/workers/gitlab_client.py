from __future__ import annotations

from dataclasses import dataclass

import gitlab


@dataclass
class MRResult:
    iid: int
    url: str
    source_branch: str
    pipeline_id: int | None


class GitLabClient:
    def __init__(self, url: str, token: str):
        self._gl = gitlab.Gitlab(url, private_token=token)

    def ensure_branch(self, project_id: str, source_branch: str, target_branch: str) -> None:
        project = self._gl.projects.get(project_id)
        existing = {b.name for b in project.branches.list(all=True)}
        if source_branch not in existing:
            project.branches.create({"branch": source_branch, "ref": target_branch})

    def commit_file(
        self,
        project_id: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
    ) -> None:
        project = self._gl.projects.get(project_id)
        try:
            project.files.get(file_path=file_path, ref=branch)
            project.files.update(
                file_path=file_path,
                new_data={
                    "branch": branch,
                    "content": content,
                    "commit_message": commit_message,
                },
            )
        except Exception:
            project.files.create(
                {
                    "file_path": file_path,
                    "branch": branch,
                    "content": content,
                    "commit_message": commit_message,
                }
            )

    def create_or_update_mr(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        labels: list[str],
    ) -> MRResult:
        project = self._gl.projects.get(project_id)
        existing = project.mergerequests.list(
            source_branch=source_branch,
            target_branch=target_branch,
            state="opened",
        )
        if existing:
            mr = existing[0]
            mr.description = description
            mr.save()
        else:
            mr = project.mergerequests.create(
                {
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "title": title,
                    "description": description,
                    "labels": labels,
                }
            )
        pipelines = mr.pipelines.list()
        pipeline_id = pipelines[0].id if pipelines else None
        return MRResult(
            iid=mr.iid,
            url=mr.web_url,
            source_branch=source_branch,
            pipeline_id=pipeline_id,
        )

    def get_file_content(self, project_id: str, file_path: str, ref: str) -> str:
        project = self._gl.projects.get(project_id)
        f = project.files.get(file_path=file_path, ref=ref)
        return f.decode().decode()

    def get_mr_state(self, project_id: str, mr_iid: int) -> dict:
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)
        pipelines = mr.pipelines.list()
        return {
            "state": mr.state,
            "pipeline_status": pipelines[0].status.upper() if pipelines else "UNKNOWN",
            "pipeline_id": pipelines[0].id if pipelines else None,
        }
