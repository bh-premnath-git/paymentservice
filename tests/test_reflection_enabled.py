import os
import sys
import asyncio
import contextlib
from unittest import mock

import pytest
from grpc import aio
from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))


class _DummySettings:
    database_url = "sqlite+aiosqlite:///:memory:"
    redis_url = "redis://localhost:6379/0"


@pytest.mark.asyncio
async def test_reflection_lists_payment_service():
    allowed_env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
    with mock.patch.dict(os.environ, allowed_env, clear=True):
        with mock.patch("config.get_settings", return_value=_DummySettings()):
            from main import serve_grpc  # type: ignore  # noqa: E402
            from payment.v1 import payment_pb2  # type: ignore  # noqa: E402

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    started = asyncio.Event()
    port = 50052
    task = asyncio.create_task(
        serve_grpc(sessionmaker, None, bind=f"localhost:{port}", started_event=started)
    )
    await started.wait()
    try:
        async with aio.insecure_channel(f"localhost:{port}") as channel:
            stub = reflection_pb2_grpc.ServerReflectionStub(channel)
            request = reflection_pb2.ServerReflectionRequest(list_services="")
            call = stub.ServerReflectionInfo(iter([request]))
            response = await call.read()
            services = [s.name for s in response.list_services_response.service]
            assert (
                payment_pb2.DESCRIPTOR.services_by_name["PaymentService"].full_name
                in services
            )
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await engine.dispose()
