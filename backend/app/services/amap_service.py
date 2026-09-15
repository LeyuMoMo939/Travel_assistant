"""高德开放平台 REST API 封装"""
import logging

import httpx

from app.config import get_settings
from app.models.schemas import POIInfo, Location, WeatherInfo

logger = logging.getLogger(__name__)

BASE_URL = "https://restapi.amap.com/v3"


def _key() -> str:
    """取配置里的 Key"""
    key = get_settings().amap_api_key
    if not key:
        raise ValueError("高德 API Key 未配置,请在 .env 中设置 AMAP_API_KEY")
    return key


def _check(data: dict, what: str) -> dict:
    """统一检查高德的返回状态。

    高德用 status=1 表示成功,失败时 info 里是原因
    (INVALID_USER_KEY / DAILY_QUERY_OVER_LIMIT / INVALID_PARAMS ...)。
    不检查的话这些错误会被下游当成「这个城市没有数据」,静默吞掉 ——
    Key 过期时用户会看到一份凭空生成的行程而毫无提示。
    """
    if str(data.get("status")) != "1":
        logger.error("高德 %s 失败: info=%s infocode=%s",
                     what, data.get("info"), data.get("infocode"))
        raise RuntimeError(f"高德{what}失败:{data.get('info')}(infocode={data.get('infocode')})")
    return data


async def search_poi(keywords: str, city: str, limit: int = 8) -> list[POIInfo]:
    """POI 文本搜索"""
    params = {
        "key": _key(),
        "keywords": keywords,
        "city": city,
        "citylimit": "true",
        "offset": limit,
        "extensions": "base",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/place/text", params=params)
        data = _check(resp.json(), "POI 搜索")

    # 遍历清洗
    pois = []
    for p in data.get("pois") or []:
        loc = None
        if p.get("location"):
            lng, lat = p["location"].split(",")[:2]
            loc = Location(longitude=float(lng), latitude=float(lat))
        pois.append(POIInfo(
            name=p.get("name", ""),
            address=p.get("address", "") or "",
            location=loc,
            tel=p.get("tel") or None,
            type=p.get("type", ""),
        ))
    return pois


async def _get_adcode(city: str) -> str | None:
    """获取城市的行政区划代码"""
    params = {
        "key": _key(),
        "keywords": city,
        "subdistrict": 0,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/config/district", params=params)
        data = _check(resp.json(), "行政区划查询")

    districts = data.get("districts") or []
    # 高德在查不到时会返回空数组而不是 null,所以两层都要兜
    return (districts[0].get("adcode") or None) if districts else None


async def get_weather(city: str) -> list[WeatherInfo]:
    """获取城市的天气预报(高德只提供「今天起 4 天」)"""

    # ---- 城市名 -> 行政区划代码 ----
    adcode = await _get_adcode(city)
    if not adcode:
        logger.warning("查不到城市 %s 的行政区划代码,跳过天气", city)
        return []

    # ---- 行政区划代码 -> 天气预报 ----
    params = {
        "key": _key(),
        "city": adcode,
        "extensions": "all",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/weather/weatherInfo", params=params)
        data = _check(resp.json(), "天气预报")

    # forecasts 存在但为空数组时,旧的 data.get("forecasts", [{}])[0] 会 IndexError
    forecasts = data.get("forecasts") or []
    casts = (forecasts[0].get("casts") or []) if forecasts else []

    # 字段名以高德 forecast 接口实际返回为准:
    # dayweather / nightweather / daywind / nightwind / daypower / nightpower
    # (winddirection / windpower 是「实况天气」的字段,预报接口里没有)
    return [
        WeatherInfo(
            date=f.get("date", ""),
            day_weather=f.get("dayweather", ""),
            night_weather=f.get("nightweather", ""),
            day_temp=f.get("daytemp", 0),
            night_temp=f.get("nighttemp", 0),
            wind_direction=f.get("daywind", ""),
            wind_power=f.get("daypower", ""),
        )
        for f in casts
    ]
