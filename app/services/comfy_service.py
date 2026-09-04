from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.config import AppSettings
from app.core.context import get_request_id
from app.core.exceptions import AppError
from app.db.unit_of_work import UowFactory
from app.executors.base import CommandResult, Executor
from app.models.comfy import CommandRun, Host, Instance, ModelRoot
from app.schemas.comfy import (
    ComfyCatalogResponse,
    HostCreateRequest,
    HostListResponse,
    HostResponse,
    InstanceCreateRequest,
    InstanceInstallRequest,
    InstanceLaunchConfigUpdateRequest,
    InstanceListResponse,
    InstanceLogsResponse,
    InstanceReadyResponse,
    InstanceResponse,
    InstanceStatusResponse,
    ModelRootCheckResponse,
    ModelRootCreateRequest,
    ModelRootListResponse,
    ModelRootResponse,
    ProbeResponse,
    RunListResponse,
    RunResponse,
)
from app.services.comfy_paths import default_model_root_path, instance_install_root, resolved_data_root, service_root
from comfyctl.catalog import catalog_payload, default_version, runtime_profile_by_id, version_by_id


def iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def host_to_response(host: Host) -> HostResponse:
    return HostResponse(
        id=host.id,
        name=host.name,
        connection=host.connection,  # type: ignore[arg-type]
        ssh_target=host.ssh_target,
        service_root=host.service_root,
        data_root=host.data_root,
        host_key_fingerprint=host.host_key_fingerprint,
        created_at=host.created_at.isoformat(),
        updated_at=host.updated_at.isoformat(),
    )


def model_root_to_response(model_root: ModelRoot) -> ModelRootResponse:
    return ModelRootResponse(
        id=model_root.id,
        host_id=model_root.host_id,
        label=model_root.label,
        path=model_root.path,
        created_at=model_root.created_at.isoformat(),
        updated_at=model_root.updated_at.isoformat(),
    )


def instance_to_response(instance: Instance, *, data_root: str, model_root_ids: list[str]) -> InstanceResponse:
    return InstanceResponse(
        id=instance.id,
        host_id=instance.host_id,
        name=instance.name,
        instance_slug=instance.instance_slug,
        install_root=instance_install_root(data_root=data_root, instance_slug=instance.instance_slug),
        comfy_ref=instance.comfy_ref,
        resolved_commit=instance.resolved_commit,
        python_version=instance.python_version,
        torch_profile=instance.torch_profile,
        comfy_port=instance.comfy_port,
        gpu_ids=list(instance.gpu_ids),
        primary_model_root_id=instance.primary_model_root_id,
        model_root_ids=model_root_ids,
        created_at=instance.created_at.isoformat(),
        updated_at=instance.updated_at.isoformat(),
        last_launched_at=iso(instance.last_launched_at),
    )


def run_to_response(run: CommandRun) -> RunResponse:
    return RunResponse(
        id=run.id,
        request_id=run.request_id,
        host_id=run.host_id,
        instance_id=run.instance_id,
        kind=run.kind,  # type: ignore[arg-type]
        phase=run.phase,
        started_at=run.started_at.isoformat(),
        ended_at=iso(run.ended_at),
        exit_code=run.exit_code,
        error_code=run.error_code,
        message=run.message,
        log_path=run.log_path,
        stderr_tail=run.stderr_tail,
    )


class ComfyCtlClient:
    def __init__(self, executor: Executor, *, root_dir: Path) -> None:
        self._executor = executor
        self._root_dir = root_dir

    async def run(self, args: list[str]) -> tuple[dict[str, Any], CommandResult]:
        result = await self._executor.run([sys.executable, "-m", "comfyctl.cli", *args])
        payload = self._parse_json(result)
        return payload, result

    def _parse_json(self, result: CommandResult) -> dict[str, Any]:
        if not result.stdout.strip():
            raise AppError("COMFYCTL_FAILED", details={"layer": "process", "stderr_tail": result.stderr[-4000:]})
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AppError(
                "COMFYCTL_FAILED",
                details={"layer": "process", "stdout_tail": result.stdout[-4000:], "stderr_tail": result.stderr[-4000:]},
            ) from exc
        if not isinstance(payload, dict):
            raise AppError("COMFYCTL_FAILED", details={"layer": "process", "stdout_tail": result.stdout[-4000:]})
        return payload


class ComfyService:
    def __init__(self, uow_factory: UowFactory, ctl: ComfyCtlClient, settings: AppSettings) -> None:
        self._uow_factory = uow_factory
        self._ctl = ctl
        self._settings = settings

    def get_catalog(self) -> ComfyCatalogResponse:
        return ComfyCatalogResponse(**catalog_payload())

    def _resolve_comfy_ref(self, *, comfy_version_id: str | None, comfy_ref: str | None) -> str:
        if comfy_version_id is not None and comfy_ref is not None:
            raise AppError(
                "REQUEST_INVALID",
                details={"field": "comfy_ref", "message": "comfy_version_id and comfy_ref cannot be used together"},
            )
        if comfy_version_id is not None:
            try:
                return str(version_by_id(comfy_version_id)["ref"])
            except KeyError as exc:
                raise AppError(
                    "REQUEST_INVALID",
                    details={"field": "comfy_version_id", "message": f"unknown comfy_version_id: {comfy_version_id}"},
                ) from exc
        if comfy_ref is not None:
            return comfy_ref
        if self._settings.comfy.default_ref:
            return self._settings.comfy.default_ref
        return str(default_version()["ref"])

    def _resolve_runtime(self, data: InstanceCreateRequest) -> tuple[str, str]:
        if data.runtime_profile_id is not None and (data.python_version is not None or data.torch_profile is not None):
            raise AppError(
                "REQUEST_INVALID",
                details={
                    "field": "runtime_profile_id",
                    "message": "runtime_profile_id cannot be mixed with python_version or torch_profile",
                },
            )
        if data.runtime_profile_id is not None:
            try:
                profile = runtime_profile_by_id(data.runtime_profile_id)
            except KeyError as exc:
                raise AppError(
                    "REQUEST_INVALID",
                    details={
                        "field": "runtime_profile_id",
                        "message": f"unknown runtime_profile_id: {data.runtime_profile_id}",
                    },
                ) from exc
            return str(profile["python_version"]), str(profile["torch_profile"])
        return data.python_version or self._settings.comfy.python_version, data.torch_profile or self._settings.comfy.torch_profile

    async def ensure_default_host(self) -> HostResponse:
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            assert uow.model_roots is not None
            host = await uow.hosts.get_by_name("local")
            if host is None:
                data_root = str(resolved_data_root(self._settings.comfy.data_root))
                host = await uow.hosts.create(
                    name="local",
                    connection="local",
                    service_root=str(service_root()),
                    data_root=data_root,
                )
                await uow.model_roots.create(host_id=host.id, label="Shared Models", path=default_model_root_path(data_root=data_root))
                await uow.commit()
            return host_to_response(host)

    async def create_host(self, data: HostCreateRequest) -> HostResponse:
        if data.connection == "ssh":
            raise AppError("EXECUTOR_UNSUPPORTED", details={"connection": data.connection})
        service_root_value = data.service_root or str(service_root())
        data_root_value = data.data_root or str(resolved_data_root(self._settings.comfy.data_root))
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            try:
                host = await uow.hosts.create(
                    name=data.name,
                    connection=data.connection,
                    service_root=service_root_value,
                    data_root=data_root_value,
                    ssh_target=data.ssh_target,
                    host_key_fingerprint=data.host_key_fingerprint,
                )
                await uow.commit()
            except IntegrityError as exc:
                await uow.rollback()
                raise AppError("HOST_NAME_CONFLICT", details={"name": data.name}) from exc
            return host_to_response(host)

    async def list_hosts(self) -> HostListResponse:
        await self.ensure_default_host()
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            return HostListResponse(hosts=[host_to_response(host) for host in await uow.hosts.list()])

    async def probe_host(self, host_id: str) -> ProbeResponse:
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            host = await uow.hosts.get(host_id)
            if host is None:
                raise AppError("HOST_NOT_FOUND", details={"host_id": host_id})
        payload, _result = await self._ctl.run(["host", "probe", "--data-root", host.data_root, "--json"])
        return ProbeResponse(ok=bool(payload.get("ok")), layer=str(payload.get("layer", "host")), data=dict(payload.get("data", {})))

    async def create_model_root(self, data: ModelRootCreateRequest) -> ModelRootResponse:
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            assert uow.model_roots is not None
            host = await uow.hosts.get(data.host_id)
            if host is None:
                raise AppError("HOST_NOT_FOUND", details={"host_id": data.host_id})
            try:
                model_root = await uow.model_roots.create(host_id=data.host_id, label=data.label, path=data.path)
                await uow.commit()
            except IntegrityError as exc:
                await uow.rollback()
                raise AppError("MODEL_ROOT_CONFLICT", details={"host_id": data.host_id, "path": data.path}) from exc
            return model_root_to_response(model_root)

    async def list_model_roots(self, *, host_id: str | None) -> ModelRootListResponse:
        await self.ensure_default_host()
        async with self._uow_factory() as uow:
            assert uow.model_roots is not None
            return ModelRootListResponse(
                model_roots=[model_root_to_response(item) for item in await uow.model_roots.list(host_id=host_id)]
            )

    async def check_model_root(self, model_root_id: str) -> ModelRootCheckResponse:
        async with self._uow_factory() as uow:
            assert uow.model_roots is not None
            model_root = await uow.model_roots.get(model_root_id)
            if model_root is None:
                raise AppError("MODEL_ROOT_NOT_FOUND", details={"model_root_id": model_root_id})
        payload, _result = await self._ctl.run(["model-root", "check", "--path", model_root.path, "--json"])
        return ModelRootCheckResponse(
            ok=bool(payload.get("ok")),
            path=str(payload.get("path", model_root.path)),
            exists=bool(payload.get("exists")),
            is_dir=bool(payload.get("is_dir")),
            readable=bool(payload.get("readable")),
        )

    async def create_instance(self, data: InstanceCreateRequest) -> InstanceResponse:
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            assert uow.instances is not None
            assert uow.model_roots is not None
            host = await uow.hosts.get(data.host_id)
            if host is None:
                raise AppError("HOST_NOT_FOUND", details={"host_id": data.host_id})
            if await uow.instances.get_by_host_slug(host_id=data.host_id, instance_slug=data.instance_slug) is not None:
                raise AppError("INSTANCE_SLUG_CONFLICT", details={"instance_slug": data.instance_slug})
            model_root_ids = data.model_root_ids
            if not model_root_ids:
                roots = await uow.model_roots.list(host_id=data.host_id)
                model_root_ids = [roots[0].id] if roots else []
            primary_model_root_id = data.primary_model_root_id or (model_root_ids[0] if model_root_ids else None)
            if primary_model_root_id is not None and primary_model_root_id not in model_root_ids:
                raise AppError("MODEL_ROOT_NOT_FOUND", details={"model_root_id": primary_model_root_id})
            for model_root_id in model_root_ids:
                model_root = await uow.model_roots.get(model_root_id)
                if model_root is None or model_root.host_id != data.host_id:
                    raise AppError("MODEL_ROOT_NOT_FOUND", details={"model_root_id": model_root_id})
            comfy_ref = self._resolve_comfy_ref(comfy_version_id=data.comfy_version_id, comfy_ref=data.comfy_ref)
            python_version, torch_profile = self._resolve_runtime(data)
            instance = await uow.instances.create(
                host_id=data.host_id,
                name=data.name,
                instance_slug=data.instance_slug,
                comfy_ref=comfy_ref,
                python_version=python_version,
                torch_profile=torch_profile,
                comfy_port=data.comfy_port or self._settings.comfy.instance_port_start,
                gpu_ids=data.gpu_ids,
                primary_model_root_id=primary_model_root_id,
            )
            await uow.instances.set_model_roots(instance_id=instance.id, model_root_ids=model_root_ids)
            await uow.commit()
            return instance_to_response(instance, data_root=host.data_root, model_root_ids=model_root_ids)

    async def _status_payload(self, host: Host, instance: Instance) -> dict[str, Any]:
        payload, _result = await self._ctl.run(
            [
                "instance",
                "status",
                "--id",
                instance.id,
                "--slug",
                instance.instance_slug,
                "--data-root",
                host.data_root,
                "--host",
                self._settings.comfy.bind_host,
                "--port",
                str(instance.comfy_port),
                "--json",
            ]
        )
        if not payload.get("ok"):
            raise AppError(str(payload.get("error_code", "COMFYCTL_FAILED")), details=payload)
        return payload

    async def update_instance_launch_config(
        self, instance_id: str, data: InstanceLaunchConfigUpdateRequest
    ) -> InstanceResponse:
        if not data.model_fields_set:
            raise AppError("REQUEST_INVALID", details={"message": "at least one launch config field is required"})
        for field in ("comfy_port", "gpu_ids", "model_root_ids"):
            if field in data.model_fields_set and getattr(data, field) is None:
                raise AppError("REQUEST_INVALID", details={"field": field, "message": "null is not allowed"})
        host, instance, current_model_root_ids, _model_roots = await self._instance_context(instance_id)
        status_payload = await self._status_payload(host, instance)
        status_data = dict(status_payload.get("data", {}))
        if status_data.get("process_alive") is True:
            raise AppError("INSTANCE_RUNNING", details={"instance_id": instance.id, "layer": "process"})

        final_model_root_ids = data.model_root_ids if "model_root_ids" in data.model_fields_set else current_model_root_ids
        if "primary_model_root_id" in data.model_fields_set:
            final_primary_model_root_id = data.primary_model_root_id
        else:
            final_primary_model_root_id = instance.primary_model_root_id
            if final_primary_model_root_id is not None and final_primary_model_root_id not in final_model_root_ids:
                final_primary_model_root_id = final_model_root_ids[0] if final_model_root_ids else None
        if final_primary_model_root_id is not None and final_primary_model_root_id not in final_model_root_ids:
            raise AppError("MODEL_ROOT_NOT_FOUND", details={"model_root_id": final_primary_model_root_id})

        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            assert uow.instances is not None
            assert uow.model_roots is not None
            current = await uow.instances.get(instance.id)
            if current is None:
                raise AppError("INSTANCE_NOT_FOUND", details={"instance_id": instance.id})
            for model_root_id in final_model_root_ids:
                model_root = await uow.model_roots.get(model_root_id)
                if model_root is None or model_root.host_id != host.id:
                    raise AppError("MODEL_ROOT_NOT_FOUND", details={"model_root_id": model_root_id})
            await uow.instances.update_launch_config(
                instance_id=instance.id,
                comfy_port=data.comfy_port if data.comfy_port is not None else instance.comfy_port,
                gpu_ids=data.gpu_ids if data.gpu_ids is not None else list(instance.gpu_ids),
                primary_model_root_id=final_primary_model_root_id,
            )
            await uow.instances.set_model_roots(instance_id=instance.id, model_root_ids=final_model_root_ids)
            await uow.commit()
        return await self.get_instance(instance.id)

    async def _instance_context(self, instance_id: str) -> tuple[Host, Instance, list[str], list[ModelRoot]]:
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            assert uow.instances is not None
            assert uow.model_roots is not None
            instance = await uow.instances.get(instance_id)
            if instance is None:
                raise AppError("INSTANCE_NOT_FOUND", details={"instance_id": instance_id})
            host = await uow.hosts.get(instance.host_id)
            if host is None:
                raise AppError("HOST_NOT_FOUND", details={"host_id": instance.host_id})
            model_root_ids = await uow.instances.model_root_ids(instance_id=instance.id)
            model_roots: list[ModelRoot] = []
            for model_root_id in model_root_ids:
                model_root = await uow.model_roots.get(model_root_id)
                if model_root is not None:
                    model_roots.append(model_root)
            return host, instance, model_root_ids, model_roots

    async def get_instance(self, instance_id: str) -> InstanceResponse:
        host, instance, model_root_ids, _model_roots = await self._instance_context(instance_id)
        return instance_to_response(instance, data_root=host.data_root, model_root_ids=model_root_ids)

    async def list_instances(self, *, host_id: str | None) -> InstanceListResponse:
        await self.ensure_default_host()
        async with self._uow_factory() as uow:
            assert uow.hosts is not None
            assert uow.instances is not None
            rows: list[InstanceResponse] = []
            for instance in await uow.instances.list(host_id=host_id):
                host = await uow.hosts.get(instance.host_id)
                if host is None:
                    raise AppError("HOST_NOT_FOUND", details={"host_id": instance.host_id})
                model_root_ids = await uow.instances.model_root_ids(instance_id=instance.id)
                rows.append(instance_to_response(instance, data_root=host.data_root, model_root_ids=model_root_ids))
            return InstanceListResponse(instances=rows)

    async def _record_run(self, *, host_id: str, instance_id: str | None, kind: str) -> str:
        async with self._uow_factory() as uow:
            assert uow.command_runs is not None
            run = await uow.command_runs.create(
                request_id=get_request_id(),
                host_id=host_id,
                instance_id=instance_id,
                kind=kind,
            )
            await uow.commit()
            return run.id

    async def _finish_run(self, *, run_id: str, payload: dict[str, Any], result: CommandResult) -> None:
        ok = bool(payload.get("ok"))
        async with self._uow_factory() as uow:
            assert uow.command_runs is not None
            await uow.command_runs.finish(
                run_id=run_id,
                phase="completed" if ok else "failed",
                exit_code=result.exit_code,
                error_code=None if ok else str(payload.get("error_code", "COMFYCTL_FAILED")),
                message=str(payload.get("message", "")) if payload.get("message") else None,
                log_path=str(payload.get("log_path", "")) if payload.get("log_path") else None,
                stderr_tail=str(payload.get("stderr_tail", "")) if payload.get("stderr_tail") else result.stderr[-4000:],
            )
            await uow.commit()

    async def _run_recorded(self, *, run_id: str, args: list[str]) -> tuple[dict[str, Any], CommandResult]:
        try:
            payload, result = await self._ctl.run(args)
        except AppError as exc:
            async with self._uow_factory() as uow:
                assert uow.command_runs is not None
                await uow.command_runs.finish(
                    run_id=run_id,
                    phase="failed",
                    exit_code=1,
                    error_code=exc.code,
                    message=exc.code,
                    log_path=None,
                    stderr_tail=str(exc.details.get("stderr_tail", "")) if exc.details else None,
                )
                await uow.commit()
            raise
        await self._finish_run(run_id=run_id, payload=payload, result=result)
        return payload, result

    async def install_instance(self, instance_id: str, data: InstanceInstallRequest, *, kind: str = "install") -> RunResponse:
        host, instance, _model_root_ids, _model_roots = await self._instance_context(instance_id)
        comfy_ref = (
            self._resolve_comfy_ref(comfy_version_id=data.comfy_version_id, comfy_ref=data.comfy_ref)
            if data.comfy_version_id is not None or data.comfy_ref is not None
            else instance.comfy_ref
        )
        run_id = await self._record_run(host_id=host.id, instance_id=instance.id, kind=kind)
        payload, _result = await self._run_recorded(
            run_id=run_id,
            args=[
                "instance",
                "install",
                "--id",
                instance.id,
                "--slug",
                instance.instance_slug,
                "--data-root",
                host.data_root,
                "--repo",
                self._settings.comfy.repo_url,
                "--ref",
                comfy_ref,
                "--python",
                instance.python_version,
                "--torch-profile",
                instance.torch_profile,
                "--json",
            ],
        )
        if not payload.get("ok"):
            raise AppError(str(payload.get("error_code", "COMFYCTL_FAILED")), details=payload)
        async with self._uow_factory() as uow:
            assert uow.instances is not None
            await uow.instances.update_install_result(
                instance_id=instance.id,
                comfy_ref=comfy_ref,
                resolved_commit=str(payload.get("resolved_commit", "")) or None,
            )
            await uow.commit()
        if data.restart:
            await self.start_instance(instance_id)
        return await self.get_run(run_id)

    async def start_instance(self, instance_id: str) -> RunResponse:
        host, instance, _model_root_ids, model_roots = await self._instance_context(instance_id)
        run_id = await self._record_run(host_id=host.id, instance_id=instance.id, kind="start")
        args = [
            "instance",
            "start",
            "--id",
            instance.id,
            "--slug",
            instance.instance_slug,
            "--data-root",
            host.data_root,
            "--host",
            self._settings.comfy.bind_host,
            "--port",
            str(instance.comfy_port),
            "--json",
        ]
        for model_root in model_roots:
            args.extend(["--extra-model-paths", model_root.path])
        for gpu_id in instance.gpu_ids:
            args.extend(["--gpu", gpu_id])
        payload, _result = await self._run_recorded(run_id=run_id, args=args)
        if not payload.get("ok"):
            raise AppError(str(payload.get("error_code", "COMFYCTL_FAILED")), details=payload)
        async with self._uow_factory() as uow:
            assert uow.instances is not None
            await uow.instances.mark_launched(instance_id=instance.id)
            await uow.commit()
        return await self.get_run(run_id)

    async def stop_instance(self, instance_id: str) -> RunResponse:
        host, instance, _model_root_ids, _model_roots = await self._instance_context(instance_id)
        run_id = await self._record_run(host_id=host.id, instance_id=instance.id, kind="stop")
        payload, _result = await self._run_recorded(
            run_id=run_id,
            args=[
                "instance",
                "stop",
                "--id",
                instance.id,
                "--slug",
                instance.instance_slug,
                "--data-root",
                host.data_root,
                "--json",
            ],
        )
        if not payload.get("ok"):
            raise AppError(str(payload.get("error_code", "COMFYCTL_FAILED")), details=payload)
        return await self.get_run(run_id)

    async def status_instance(self, instance_id: str) -> InstanceStatusResponse:
        host, instance, _model_root_ids, _model_roots = await self._instance_context(instance_id)
        payload = await self._status_payload(host, instance)
        return InstanceStatusResponse(
            ok=bool(payload.get("ok")),
            instance_id=instance.id,
            layer=str(payload.get("layer", "process")),
            data=dict(payload.get("data", {})),
        )

    async def ready_instance(self, instance_id: str) -> InstanceReadyResponse:
        host, instance, _model_root_ids, _model_roots = await self._instance_context(instance_id)
        payload, _result = await self._ctl.run(
            [
                "instance",
                "ready",
                "--id",
                instance.id,
                "--slug",
                instance.instance_slug,
                "--data-root",
                host.data_root,
                "--host",
                self._settings.comfy.bind_host,
                "--port",
                str(instance.comfy_port),
                "--json",
            ]
        )
        return InstanceReadyResponse(
            ready=bool(payload.get("ready")),
            instance_id=instance.id,
            layer=str(payload.get("layer", "comfy")),
            data=dict(payload.get("data", {})),
        )

    async def logs_instance(self, instance_id: str, *, tail: int) -> InstanceLogsResponse:
        host, instance, _model_root_ids, _model_roots = await self._instance_context(instance_id)
        payload, _result = await self._ctl.run(
            [
                "instance",
                "logs",
                "--id",
                instance.id,
                "--slug",
                instance.instance_slug,
                "--data-root",
                host.data_root,
                "--tail",
                str(tail),
            ]
        )
        return InstanceLogsResponse(
            instance_id=instance.id,
            log_path=str(payload.get("log_path", "")),
            lines=list(payload.get("lines", [])),
        )

    async def list_runs(self, *, instance_id: str | None) -> RunListResponse:
        async with self._uow_factory() as uow:
            assert uow.command_runs is not None
            return RunListResponse(runs=[run_to_response(run) for run in await uow.command_runs.list(instance_id=instance_id)])

    async def get_run(self, run_id: str) -> RunResponse:
        async with self._uow_factory() as uow:
            assert uow.command_runs is not None
            run = await uow.command_runs.get(run_id)
            if run is None:
                raise AppError("RUN_NOT_FOUND", details={"run_id": run_id})
            return run_to_response(run)
