import asyncio

from PIL import Image
import pytest

from sdk.server.config import SamplePolicy
from sdk.server.frame_sampler import FrameSampler


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def image(color: str = "red", size: tuple[int, int] = (64, 48)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_accept_throttles_before_replacing_latest_frame() -> None:
    clock = FakeClock()
    sampler = FrameSampler(SamplePolicy(max_fps=2), clock=clock)

    assert sampler.accept_image(image("red")) is True
    first = sampler.latest_raw
    clock.value = 0.1
    assert sampler.accept_image(image("blue")) is False
    assert sampler.latest_raw is first
    clock.value = 0.6
    assert sampler.accept_image(image("green")) is True
    assert sampler.latest_raw is not first
    assert sampler.accepted_count == 2


@pytest.mark.asyncio
async def test_single_look_returns_one_downscaled_jpeg() -> None:
    clock = FakeClock()
    sampler = FrameSampler(SamplePolicy(image_max_side=1000), clock=clock)
    sampler.accept_image(image(size=(2000, 1000)))

    result = await sampler.look(reason="read the card")

    assert len(result.images) == 1
    assert result.images[0].size == (1000, 500)
    assert result.images[0].jpeg.startswith(b"\xff\xd8")
    assert result.note is None


@pytest.mark.asyncio
async def test_motion_look_returns_recent_burst_in_capture_order() -> None:
    clock = FakeClock()
    sampler = FrameSampler(
        SamplePolicy(max_fps=10, burst_count=3, burst_window_ms=100), clock=clock
    )
    sampler.accept_image(image("red"))

    look_task = asyncio.create_task(sampler.look(reason="check motion", motion=True))
    await asyncio.sleep(0)
    clock.value = 0.2
    sampler.accept_image(image("green"))
    await asyncio.sleep(0)
    clock.value = 0.4
    sampler.accept_image(image("blue"))
    result = await look_task

    assert len(result.images) == 3
    assert [frame.captured_at for frame in result.images] == [0.0, 0.2, 0.4]


@pytest.mark.asyncio
async def test_motion_look_reuses_latest_when_stream_is_slow() -> None:
    sampler = FrameSampler(
        SamplePolicy(burst_count=3, burst_window_ms=10), clock=FakeClock()
    )
    sampler.accept_image(image())

    result = await sampler.look(reason="check motion", motion=True)

    assert len(result.images) == 3
    assert result.reused_last_frame is True


@pytest.mark.asyncio
async def test_budget_cap_reuses_last_encoded_frame_without_more_spend() -> None:
    sampler = FrameSampler(SamplePolicy(max_frames_per_min=1), clock=FakeClock())
    sampler.accept_image(image())
    first = await sampler.look(reason="first")

    second = await sampler.look(reason="second")

    assert sampler.images_sent == 1
    assert second.images[0].jpeg == first.images[0].jpeg
    assert second.reused_last_frame is True
    assert "budget exhausted" in second.note.lower()


@pytest.mark.asyncio
async def test_look_without_camera_returns_sentinel_note() -> None:
    sampler = FrameSampler(SamplePolicy(), clock=FakeClock())

    result = await sampler.look(reason="read card")

    assert result.images == []
    assert result.note == "(no camera frame available)"
    assert sampler.images_sent == 0
