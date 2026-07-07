from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import tracecat.registry.common as registry_common
from tracecat.registry.constants import DEFAULT_LOCAL_REGISTRY_ORIGIN
from tracecat.registry.repositories.schemas import RegistryRepositoryCreate


@pytest.mark.anyio
async def test_ensure_org_repositories_skips_when_custom_registry_not_entitled(
    test_role,
) -> None:
    session = AsyncMock()

    with (
        patch.object(
            registry_common.config, "TRACECAT__LOCAL_REPOSITORY_ENABLED", True
        ),
        patch.object(registry_common.config, "TRACECAT__LOCAL_REPOSITORY_PATH", "/tmp"),
        patch.object(
            registry_common,
            "get_setting",
            new=AsyncMock(return_value="git+ssh://git@github.com/acme/repo.git"),
        ),
        patch.object(
            registry_common,
            "is_org_entitled",
            new=AsyncMock(return_value=False),
        ) as mock_is_org_entitled,
        patch.object(registry_common, "RegistryReposService") as MockReposService,
    ):
        await registry_common.ensure_org_repositories(session, test_role)

    mock_is_org_entitled.assert_awaited_once()
    MockReposService.assert_not_called()


@pytest.mark.anyio
async def test_ensure_org_repositories_creates_local_and_remote_when_entitled(
    test_role,
) -> None:
    session = AsyncMock()
    remote_url = "git+ssh://git@github.com/acme/repo.git"

    with (
        patch.object(
            registry_common.config, "TRACECAT__LOCAL_REPOSITORY_ENABLED", True
        ),
        patch.object(registry_common.config, "TRACECAT__LOCAL_REPOSITORY_PATH", "/tmp"),
        patch.object(
            registry_common,
            "get_setting",
            new=AsyncMock(return_value=remote_url),
        ),
        patch.object(
            registry_common,
            "is_org_entitled",
            new=AsyncMock(return_value=True),
        ),
        patch.object(registry_common, "RegistryReposService") as MockReposService,
    ):
        mock_repos_service = AsyncMock()
        mock_repos_service.get_repository.return_value = None
        MockReposService.return_value = mock_repos_service

        await registry_common.ensure_org_repositories(session, test_role)

    expected = {
        DEFAULT_LOCAL_REGISTRY_ORIGIN,
        remote_url,
    }
    created = {
        call.args[0].origin
        for call in mock_repos_service.create_repository.await_args_list
        if isinstance(call.args[0], RegistryRepositoryCreate)
    }
    assert created == expected


@pytest.mark.anyio
async def test_ensure_org_repositories_sanitizes_remote_url_before_logging_and_create(
    test_role,
) -> None:
    session = AsyncMock()
    remote_url = "git+ssh://git:secret@github.com/acme/repo.git"
    cleaned_url = "git+ssh://git@github.com/acme/repo.git"

    with (
        patch.object(
            registry_common.config, "TRACECAT__LOCAL_REPOSITORY_ENABLED", False
        ),
        patch.object(
            registry_common,
            "get_setting",
            new=AsyncMock(return_value=remote_url),
        ),
        patch.object(
            registry_common,
            "is_org_entitled",
            new=AsyncMock(return_value=True),
        ),
        patch.object(registry_common, "RegistryReposService") as MockReposService,
        patch.object(registry_common, "logger") as mock_logger,
    ):
        mock_repos_service = AsyncMock()
        mock_repos_service.get_repository.return_value = None
        MockReposService.return_value = mock_repos_service

        await registry_common.ensure_org_repositories(session, test_role)

    mock_repos_service.get_repository.assert_awaited_once_with(cleaned_url)
    mock_repos_service.create_repository.assert_awaited_once()
    created_repository = mock_repos_service.create_repository.await_args.args[0]
    assert isinstance(created_repository, RegistryRepositoryCreate)
    assert created_repository.origin == cleaned_url

    info_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert any(cleaned_url in call for call in info_calls)
    assert all("secret" not in call for call in info_calls)
    assert all(remote_url not in call for call in info_calls)
