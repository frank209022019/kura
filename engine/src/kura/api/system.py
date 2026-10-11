"""What this PC has to work with, for the setup's quick graphics card check."""

from fastapi import APIRouter

from kura import system
from kura.api.common import ApiModel

router = APIRouter()


class System(ApiModel):
    graphics_card: str | None  # None when Windows wouldn't say


@router.get("/system")
def this_pc() -> System:
    return System(graphics_card=system.graphics_card())
