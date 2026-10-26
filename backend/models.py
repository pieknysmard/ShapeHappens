from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Settings(BaseModel):
    mode: Literal['cookie', 'roller'] = 'cookie'
    tolerance: int = Field(30, ge=0, le=100)
    size: float = Field(80, ge=5, le=500)
    size_axis: Literal['width', 'height'] = 'width'
    red_height: float = Field(7, ge=0.4, le=50)
    green_height: float = Field(5, ge=0.4, le=50)
    backing: float = Field(1, ge=0.4, le=10)
    frame_offset: float = Field(3, ge=0.4, le=20)
    frame_height: float = Field(2, ge=0.4, le=20)
    min_wall: float = Field(0.8, ge=0.4, le=5)
    diameter: float = Field(40, ge=8, le=200)
    length: float = Field(100, ge=5, le=500)
    depth: float = Field(1, ge=0.1, le=20)
    bore: float = Field(0, ge=0, le=180)
    quality: Literal['draft', 'standard', 'fine'] = 'standard'
    smoothing: float = Field(0.06, ge=0, le=1)
    invert: bool = False
    seamless: bool = False
    proportions: bool = False

    @model_validator(mode='after')
    def geometry_limits(self):
        if self.mode == 'cookie' and self.green_height >= self.red_height:
            raise ValueError('Green detail height must be below the red cutting edge.')
        if self.mode == 'roller' and self.diameter / 2 - self.depth - self.bore / 2 < self.min_wall:
            raise ValueError('Recesses leave less than the minimum wall above the bore/axis.')
        return self
