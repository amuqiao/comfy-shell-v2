from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.operations import operation_responses
from app.core.config.settings import ROOT_DIR
from app.core.context import get_request_id, get_trace_id
from app.core.security import Principal, get_current_principal
from app.db.unit_of_work import uow_factory_from_session_factory
from app.executors.local import LocalExecutor
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
    InstanceStartRequest,
    InstanceStatusResponse,
    InstanceStopRequest,
    ModelRootCheckResponse,
    ModelRootCreateRequest,
    ModelRootListResponse,
    ModelRootResponse,
    ProbeResponse,
    RunListResponse,
    RunResponse,
)
from app.schemas.envelope import SuccessEnvelope, success_envelope
from app.services.comfy_service import ComfyCtlClient, ComfyService

router = APIRouter(tags=["comfy"])


def get_comfy_service(request: Request) -> ComfyService:
    session_factory = request.app.state.db_session_factory
    executor = LocalExecutor(root_dir=ROOT_DIR)
    ctl = ComfyCtlClient(executor, root_dir=ROOT_DIR)
    return ComfyService(uow_factory_from_session_factory(session_factory), ctl, request.app.state.settings)


@router.get(
    "/catalog",
    operation_id="get_comfy_catalog",
    response_model=SuccessEnvelope[ComfyCatalogResponse],
    responses=operation_responses("get_comfy_catalog"),
)
async def get_comfy_catalog(
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[ComfyCatalogResponse]:
    return success_envelope(service.get_catalog(), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/hosts",
    operation_id="list_hosts",
    response_model=SuccessEnvelope[HostListResponse],
    responses=operation_responses("list_hosts"),
)
async def list_hosts(
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[HostListResponse]:
    return success_envelope(await service.list_hosts(), request_id=get_request_id(), trace_id=get_trace_id())


@router.post(
    "/hosts",
    operation_id="create_host",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[HostResponse],
    responses=operation_responses("create_host"),
)
async def create_host(
    data: HostCreateRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[HostResponse]:
    return success_envelope(await service.create_host(data), request_id=get_request_id(), trace_id=get_trace_id())


@router.post(
    "/hosts/{host_id}/probe",
    operation_id="probe_host",
    response_model=SuccessEnvelope[ProbeResponse],
    responses=operation_responses("probe_host"),
)
async def probe_host(
    host_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[ProbeResponse]:
    return success_envelope(await service.probe_host(host_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/model-roots",
    operation_id="list_model_roots",
    response_model=SuccessEnvelope[ModelRootListResponse],
    responses=operation_responses("list_model_roots"),
)
async def list_model_roots(
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
    host_id: str | None = None,
) -> SuccessEnvelope[ModelRootListResponse]:
    return success_envelope(
        await service.list_model_roots(host_id=host_id), request_id=get_request_id(), trace_id=get_trace_id()
    )


@router.post(
    "/model-roots",
    operation_id="create_model_root",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[ModelRootResponse],
    responses=operation_responses("create_model_root"),
)
async def create_model_root(
    data: ModelRootCreateRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[ModelRootResponse]:
    return success_envelope(await service.create_model_root(data), request_id=get_request_id(), trace_id=get_trace_id())


@router.post(
    "/model-roots/{model_root_id}/check",
    operation_id="check_model_root",
    response_model=SuccessEnvelope[ModelRootCheckResponse],
    responses=operation_responses("check_model_root"),
)
async def check_model_root(
    model_root_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[ModelRootCheckResponse]:
    return success_envelope(await service.check_model_root(model_root_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/instances",
    operation_id="list_instances",
    response_model=SuccessEnvelope[InstanceListResponse],
    responses=operation_responses("list_instances"),
)
async def list_instances(
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
    host_id: str | None = None,
) -> SuccessEnvelope[InstanceListResponse]:
    return success_envelope(
        await service.list_instances(host_id=host_id), request_id=get_request_id(), trace_id=get_trace_id()
    )


@router.post(
    "/instances",
    operation_id="create_instance",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[InstanceResponse],
    responses=operation_responses("create_instance"),
)
async def create_instance(
    data: InstanceCreateRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[InstanceResponse]:
    return success_envelope(await service.create_instance(data), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/instances/{instance_id}",
    operation_id="get_instance",
    response_model=SuccessEnvelope[InstanceResponse],
    responses=operation_responses("get_instance"),
)
async def get_instance(
    instance_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[InstanceResponse]:
    return success_envelope(await service.get_instance(instance_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.patch(
    "/instances/{instance_id}/launch-config",
    operation_id="update_instance_launch_config",
    response_model=SuccessEnvelope[InstanceResponse],
    responses=operation_responses("update_instance_launch_config"),
)
async def update_instance_launch_config(
    instance_id: str,
    data: InstanceLaunchConfigUpdateRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[InstanceResponse]:
    return success_envelope(
        await service.update_instance_launch_config(instance_id, data),
        request_id=get_request_id(),
        trace_id=get_trace_id(),
    )


@router.post(
    "/instances/{instance_id}/install",
    operation_id="install_instance",
    response_model=SuccessEnvelope[RunResponse],
    responses=operation_responses("install_instance"),
)
async def install_instance(
    instance_id: str,
    data: InstanceInstallRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[RunResponse]:
    return success_envelope(
        await service.install_instance(instance_id, data, kind="install"),
        request_id=get_request_id(),
        trace_id=get_trace_id(),
    )


@router.post(
    "/instances/{instance_id}/reinstall",
    operation_id="reinstall_instance",
    response_model=SuccessEnvelope[RunResponse],
    responses=operation_responses("reinstall_instance"),
)
async def reinstall_instance(
    instance_id: str,
    data: InstanceInstallRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[RunResponse]:
    return success_envelope(
        await service.install_instance(instance_id, data, kind="reinstall"),
        request_id=get_request_id(),
        trace_id=get_trace_id(),
    )


@router.post(
    "/instances/{instance_id}/start",
    operation_id="start_instance",
    response_model=SuccessEnvelope[RunResponse],
    responses=operation_responses("start_instance"),
)
async def start_instance(
    instance_id: str,
    _data: InstanceStartRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[RunResponse]:
    return success_envelope(await service.start_instance(instance_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.post(
    "/instances/{instance_id}/stop",
    operation_id="stop_instance",
    response_model=SuccessEnvelope[RunResponse],
    responses=operation_responses("stop_instance"),
)
async def stop_instance(
    instance_id: str,
    _data: InstanceStopRequest,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[RunResponse]:
    return success_envelope(await service.stop_instance(instance_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/instances/{instance_id}/status",
    operation_id="status_instance",
    response_model=SuccessEnvelope[InstanceStatusResponse],
    responses=operation_responses("status_instance"),
)
async def status_instance(
    instance_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[InstanceStatusResponse]:
    return success_envelope(await service.status_instance(instance_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/instances/{instance_id}/ready",
    operation_id="ready_instance",
    response_model=SuccessEnvelope[InstanceReadyResponse],
    responses=operation_responses("ready_instance"),
)
async def ready_instance(
    instance_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[InstanceReadyResponse]:
    return success_envelope(await service.ready_instance(instance_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/instances/{instance_id}/logs",
    operation_id="logs_instance",
    response_model=SuccessEnvelope[InstanceLogsResponse],
    responses=operation_responses("logs_instance"),
)
async def logs_instance(
    instance_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
    tail: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> SuccessEnvelope[InstanceLogsResponse]:
    return success_envelope(
        await service.logs_instance(instance_id, tail=tail), request_id=get_request_id(), trace_id=get_trace_id()
    )


@router.get(
    "/runs",
    operation_id="list_runs",
    response_model=SuccessEnvelope[RunListResponse],
    responses=operation_responses("list_runs"),
)
async def list_runs(
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
    instance_id: str | None = None,
) -> SuccessEnvelope[RunListResponse]:
    return success_envelope(await service.list_runs(instance_id=instance_id), request_id=get_request_id(), trace_id=get_trace_id())


@router.get(
    "/runs/{run_id}",
    operation_id="get_run",
    response_model=SuccessEnvelope[RunResponse],
    responses=operation_responses("get_run"),
)
async def get_run(
    run_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[ComfyService, Depends(get_comfy_service)],
) -> SuccessEnvelope[RunResponse]:
    return success_envelope(await service.get_run(run_id), request_id=get_request_id(), trace_id=get_trace_id())
