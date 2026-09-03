from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comfy import CommandRun, Host, Instance, InstanceModelRoot, ModelRoot


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        connection: str,
        service_root: str,
        data_root: str,
        ssh_target: str | None = None,
        host_key_fingerprint: str | None = None,
    ) -> Host:
        host = Host(
            name=name,
            connection=connection,
            ssh_target=ssh_target,
            service_root=service_root,
            data_root=data_root,
            host_key_fingerprint=host_key_fingerprint,
        )
        self._session.add(host)
        await self._session.flush()
        await self._session.refresh(host)
        return host

    async def get(self, host_id: str) -> Host | None:
        result = await self._session.execute(select(Host).where(Host.id == host_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Host | None:
        result = await self._session.execute(select(Host).where(Host.name == name))
        return result.scalar_one_or_none()

    async def list(self) -> list[Host]:
        result = await self._session.execute(select(Host).order_by(Host.created_at.asc(), Host.id.asc()))
        return list(result.scalars().all())


class ModelRootRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, host_id: str, label: str, path: str) -> ModelRoot:
        model_root = ModelRoot(host_id=host_id, label=label, path=path)
        self._session.add(model_root)
        await self._session.flush()
        await self._session.refresh(model_root)
        return model_root

    async def get(self, model_root_id: str) -> ModelRoot | None:
        result = await self._session.execute(select(ModelRoot).where(ModelRoot.id == model_root_id))
        return result.scalar_one_or_none()

    async def get_by_host_path(self, *, host_id: str, path: str) -> ModelRoot | None:
        result = await self._session.execute(select(ModelRoot).where(ModelRoot.host_id == host_id, ModelRoot.path == path))
        return result.scalar_one_or_none()

    async def list(self, *, host_id: str | None) -> list[ModelRoot]:
        stmt = select(ModelRoot)
        if host_id is not None:
            stmt = stmt.where(ModelRoot.host_id == host_id)
        result = await self._session.execute(stmt.order_by(ModelRoot.created_at.asc(), ModelRoot.id.asc()))
        return list(result.scalars().all())


class InstanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        host_id: str,
        name: str,
        instance_slug: str,
        comfy_ref: str,
        python_version: str,
        torch_profile: str,
        comfy_port: int,
        gpu_ids: list[str],
        primary_model_root_id: str | None,
    ) -> Instance:
        instance = Instance(
            host_id=host_id,
            name=name,
            instance_slug=instance_slug,
            comfy_ref=comfy_ref,
            python_version=python_version,
            torch_profile=torch_profile,
            comfy_port=comfy_port,
            gpu_ids=gpu_ids,
            primary_model_root_id=primary_model_root_id,
        )
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def get(self, instance_id: str) -> Instance | None:
        result = await self._session.execute(select(Instance).where(Instance.id == instance_id))
        return result.scalar_one_or_none()

    async def get_by_host_slug(self, *, host_id: str, instance_slug: str) -> Instance | None:
        result = await self._session.execute(
            select(Instance).where(Instance.host_id == host_id, Instance.instance_slug == instance_slug)
        )
        return result.scalar_one_or_none()

    async def list(self, *, host_id: str | None) -> list[Instance]:
        stmt = select(Instance)
        if host_id is not None:
            stmt = stmt.where(Instance.host_id == host_id)
        result = await self._session.execute(stmt.order_by(Instance.created_at.asc(), Instance.id.asc()))
        return list(result.scalars().all())

    async def set_model_roots(self, *, instance_id: str, model_root_ids: list[str]) -> None:
        await self._session.execute(delete(InstanceModelRoot).where(InstanceModelRoot.instance_id == instance_id))
        for model_root_id in model_root_ids:
            self._session.add(InstanceModelRoot(instance_id=instance_id, model_root_id=model_root_id))
        await self._session.flush()

    async def model_root_ids(self, *, instance_id: str) -> list[str]:
        result = await self._session.execute(
            select(InstanceModelRoot.model_root_id).where(InstanceModelRoot.instance_id == instance_id)
        )
        return list(result.scalars().all())

    async def update_install_result(
        self,
        *,
        instance_id: str,
        comfy_ref: str,
        resolved_commit: str | None,
    ) -> None:
        await self._session.execute(
            update(Instance)
            .where(Instance.id == instance_id)
            .values(comfy_ref=comfy_ref, resolved_commit=resolved_commit, updated_at=utc_now())
        )

    async def mark_launched(self, *, instance_id: str) -> None:
        now = utc_now()
        await self._session.execute(
            update(Instance).where(Instance.id == instance_id).values(last_launched_at=now, updated_at=now)
        )


class CommandRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, request_id: str, host_id: str, instance_id: str | None, kind: str) -> CommandRun:
        run = CommandRun(
            request_id=request_id,
            host_id=host_id,
            instance_id=instance_id,
            kind=kind,
            phase="running",
        )
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def get(self, run_id: str) -> CommandRun | None:
        result = await self._session.execute(select(CommandRun).where(CommandRun.id == run_id))
        return result.scalar_one_or_none()

    async def list(self, *, instance_id: str | None) -> list[CommandRun]:
        stmt = select(CommandRun)
        if instance_id is not None:
            stmt = stmt.where(CommandRun.instance_id == instance_id)
        result = await self._session.execute(stmt.order_by(CommandRun.started_at.desc(), CommandRun.id.desc()))
        return list(result.scalars().all())

    async def finish(
        self,
        *,
        run_id: str,
        phase: str,
        exit_code: int,
        error_code: str | None,
        message: str | None,
        log_path: str | None,
        stderr_tail: str | None,
    ) -> None:
        await self._session.execute(
            update(CommandRun)
            .where(CommandRun.id == run_id)
            .values(
                phase=phase,
                ended_at=utc_now(),
                exit_code=exit_code,
                error_code=error_code,
                message=message,
                log_path=log_path,
                stderr_tail=stderr_tail,
            )
        )
