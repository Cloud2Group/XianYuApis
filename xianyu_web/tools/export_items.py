import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from loguru import logger

from xianyu_web.paths import COOKIE_FILE, EXPORTS_DIR
from xianyu_web.utils.goofish_utils import generate_sign, get_session_cookies_str, trans_cookies


DEFAULT_COOKIE_FILE = str(COOKIE_FILE)
DEFAULT_OUTPUT_ROOT = str(EXPORTS_DIR)
APP_KEY = "34839810"
MTOP_VERSION = "1.0"

LOCAL_TZ = None
try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = None


HEADERS = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://www.goofish.com",
    "referer": "https://www.goofish.com/",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}


def now_label() -> str:
    if LOCAL_TZ:
        return datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_cookie(cookie: str, cookie_file: str) -> str:
    if cookie:
        return cookie.strip()
    cookie_path = Path(cookie_file).expanduser()
    if cookie_path.exists():
        return cookie_path.read_text(encoding="utf-8").strip()
    return os.getenv("XIANYU_COOKIE", "").strip() or os.getenv("GOOFISH_COOKIE", "").strip()


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def first_number(*values: Any) -> Optional[int]:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def parse_json_value(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def normalize_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin("https://www.goofish.com", url)
    return url


def unique_text(values: Iterable[Any]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        text = normalize_url(str(value).strip()) if value is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def markdown_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text.replace("\n", "\n\n")


class MtopClient:
    def __init__(self, cookie_text: str, timeout: float = 25.0):
        cookies = trans_cookies(cookie_text)
        self.user_id = first_text(cookies.get("unb"))
        if not self.user_id:
            raise RuntimeError("Cookie 里缺少 unb，请确认这是登录后的完整 Cookie")
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.timeout = timeout

    @staticmethod
    def _token_expire_time(value: str) -> int:
        parts = value.split("_")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
        return 0

    def _best_cookie_value(self, name: str) -> str:
        best_expire = -1
        best_value = ""
        fallback = ""
        for cookie in self.session.cookies:
            if cookie.name != name or not cookie.value:
                continue
            fallback = cookie.value
            if name != "_m_h5_tk":
                best_value = cookie.value
                continue
            expire_time = self._token_expire_time(cookie.value)
            if expire_time >= best_expire:
                best_expire = expire_time
                best_value = cookie.value
        return best_value or fallback

    def _dedupe_auth_cookies(self) -> None:
        # requests 会同时保存空 domain 和 .goofish.com 的同名 token。
        # 如果 Cookie 里带旧 token、签名却用新 token，MTOP 会一直报令牌过期。
        for name in ("_m_h5_tk", "_m_h5_tk_enc"):
            value = self._best_cookie_value(name)
            if not value:
                continue
            for cookie in list(self.session.cookies):
                if cookie.name != name:
                    continue
                try:
                    self.session.cookies.clear(domain=cookie.domain, path=cookie.path, name=cookie.name)
                except (KeyError, ValueError):
                    pass
            self.session.cookies.set(name, value, domain=".goofish.com", path="/")

    def _token(self) -> str:
        return self._best_cookie_value("_m_h5_tk").split("_")[0]

    def request(self, api: str, data_obj: Dict[str, Any], version: str = MTOP_VERSION) -> Dict[str, Any]:
        data_value = json.dumps(data_obj, ensure_ascii=False, separators=(",", ":"))
        url = f"https://h5api.m.goofish.com/h5/{api}/{version}/"
        last_response: Dict[str, Any] = {}
        for _ in range(3):
            self._dedupe_auth_cookies()
            timestamp = str(int(time.time() * 1000))
            params = {
                "jsv": "2.7.2",
                "appKey": APP_KEY,
                "t": timestamp,
                "sign": generate_sign(timestamp, self._token(), data_value),
                "v": version,
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": api,
                "sessionOption": "AutoLoginOnly",
                "spm_cnt": "a21ybx.personal.0.0",
            }
            response = self.session.post(
                url,
                params=params,
                data={"data": data_value},
                headers=HEADERS,
                timeout=self.timeout,
            )
            self._dedupe_auth_cookies()
            response.raise_for_status()
            last_response = response.json()
            ret = last_response.get("ret") or []
            ret_text = ret[0] if ret else ""
            if "FAIL_SYS_TOKEN_EXOIRED" in ret_text or "令牌过期" in ret_text:
                continue
            if "FAIL_SYS_SESSION_EXPIRED" in ret_text:
                raise RuntimeError("登录态已过期，请先重新扫码登录并保存 Cookie")
            return last_response
        return last_response

    def cookie_text(self) -> str:
        self._dedupe_auth_cookies()
        return get_session_cookies_str(self.session)


def ensure_success(api: str, response: Dict[str, Any]) -> Dict[str, Any]:
    ret = response.get("ret") or []
    if ret and not str(ret[0]).startswith("SUCCESS"):
        raise RuntimeError(f"接口 {api} 返回异常：{ret}")
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def extract_image_urls(item_do: Dict[str, Any], card_data: Dict[str, Any]) -> List[str]:
    values: List[Any] = []
    for image_info in item_do.get("imageInfos") or []:
        if not isinstance(image_info, dict):
            continue
        values.extend(
            [
                image_info.get("url"),
                image_info.get("picUrl"),
                image_info.get("cdnUrl"),
                image_info.get("originalUrl"),
            ]
        )
    pic_info = card_data.get("picInfo") or {}
    if isinstance(pic_info, dict):
        values.append(pic_info.get("picUrl"))
    detail_params = card_data.get("detailParams") or {}
    if isinstance(detail_params, dict):
        values.append(detail_params.get("picUrl"))
        image_infos = parse_json_value(detail_params.get("imageInfos"), [])
        if isinstance(image_infos, list):
            for image_info in image_infos:
                if isinstance(image_info, dict):
                    values.extend([image_info.get("url"), image_info.get("picUrl")])
                else:
                    values.append(image_info)
    return unique_text(values)


def extract_labels(item_do: Dict[str, Any]) -> List[str]:
    values: List[Any] = []
    for key in ("itemLabelExtList", "cpvLabels", "commonTags", "recommendTagList"):
        for tag in item_do.get(key) or []:
            if isinstance(tag, dict):
                values.extend(
                    [
                        tag.get("text"),
                        tag.get("labelName"),
                        tag.get("name"),
                        tag.get("valueName"),
                        tag.get("propertyName"),
                        tag.get("catName"),
                    ]
                )
            else:
                values.append(tag)
    return unique_text(values)


def normalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    card_data = card.get("cardData") or {}
    detail_params = card_data.get("detailParams") or {}
    if not isinstance(detail_params, dict):
        detail_params = {}
    price_info = card_data.get("priceInfo") or {}
    if not isinstance(price_info, dict):
        price_info = {}
    pic_info = card_data.get("picInfo") or {}
    if not isinstance(pic_info, dict):
        pic_info = {}
    item_id = first_text(card_data.get("id"), detail_params.get("itemId"))
    return {
        "item_id": item_id,
        "title": first_text(card_data.get("title"), detail_params.get("title")),
        "price": first_text(price_info.get("price"), detail_params.get("soldPrice")),
        "status_code": first_number(card_data.get("itemStatus")),
        "category_id": first_text(card_data.get("categoryId")),
        "main_image": normalize_url(first_text(pic_info.get("picUrl"), detail_params.get("picUrl"))),
        "url": f"https://www.goofish.com/item?id={item_id}" if item_id else normalize_url(first_text(card_data.get("detailUrl"))),
        "list_raw": card_data,
    }


def normalize_detail(
    list_item: Dict[str, Any],
    detail_data: Dict[str, Any],
    include_raw: bool,
) -> Dict[str, Any]:
    item_do = detail_data.get("itemDO") or {}
    seller_do = detail_data.get("sellerDO") or {}
    if not isinstance(item_do, dict):
        item_do = {}
    if not isinstance(seller_do, dict):
        seller_do = {}
    card_data = list_item.get("list_raw") if isinstance(list_item.get("list_raw"), dict) else {}
    item_id = first_text(item_do.get("itemId"), list_item.get("item_id"))
    image_urls = extract_image_urls(item_do, card_data)
    main_image = first_text(list_item.get("main_image"), image_urls[0] if image_urls else "")
    item = {
        "item_id": item_id,
        "title": first_text(item_do.get("title"), list_item.get("title")),
        "description": first_text(item_do.get("desc")),
        "rich_text_description": first_text(item_do.get("richTextDesc")),
        "price": first_text(item_do.get("soldPrice"), list_item.get("price")),
        "original_price": first_text(item_do.get("originalPrice")),
        "transport_fee": first_text(item_do.get("transportFee")),
        "status": first_text(item_do.get("itemStatusStr")),
        "status_code": first_number(item_do.get("itemStatus"), list_item.get("status_code")),
        "category_id": first_text(list_item.get("category_id")),
        "publish_time": first_text(item_do.get("GMT_CREATE_DATE_KEY")),
        "quantity": first_number(item_do.get("quantity")),
        "browse_count": first_number(item_do.get("browseCnt")),
        "favorite_count": first_number(item_do.get("interactFavorCnt")),
        "collect_count": first_number(item_do.get("collectCnt")),
        "want_count": first_number(item_do.get("wantCnt")),
        "sold_count": first_number(item_do.get("soldCnt")),
        "can_bargain": item_do.get("bargained"),
        "labels": extract_labels(item_do),
        "main_image": main_image,
        "image_urls": image_urls,
        "url": f"https://www.goofish.com/item?id={item_id}" if item_id else list_item.get("url", ""),
        "seller": {
            "seller_id": first_text(seller_do.get("sellerId")),
            "nick": first_text(seller_do.get("nick")),
            "city": first_text(seller_do.get("city"), seller_do.get("publishCity")),
            "signature": first_text(seller_do.get("signature")),
        },
    }
    if include_raw:
        item["raw"] = detail_data
    return item


def fetch_profile(client: MtopClient) -> Dict[str, Any]:
    response = client.request(
        "mtop.idle.web.user.page.nav",
        {"self": True, "userId": client.user_id},
    )
    data = ensure_success("mtop.idle.web.user.page.nav", response)
    return data


def fetch_item_cards(client: MtopClient, page_size: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    page_number = 1
    cards: List[Dict[str, Any]] = []
    groups: Dict[str, Any] = {}
    seen_ids = set()
    while True:
        response = client.request(
            "mtop.idle.web.xyh.item.list",
            {
                "needGroupInfo": page_number == 1,
                "pageNumber": page_number,
                "userId": client.user_id,
                "pageSize": page_size,
            },
        )
        data = ensure_success("mtop.idle.web.xyh.item.list", response)
        if page_number == 1:
            groups = {
                "item_groups": data.get("itemGroupList") or [],
                "item_topics": data.get("itemTopicList") or [],
            }
        page_cards = data.get("cardList") or []
        logger.info(f"第 {page_number} 页拿到 {len(page_cards)} 个商品\n")
        for card in page_cards:
            if not isinstance(card, dict):
                continue
            normalized = normalize_card(card)
            item_id = normalized.get("item_id")
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            cards.append(normalized)
        if not data.get("nextPage") or not page_cards:
            break
        page_number += 1
        time.sleep(0.25)
    return cards, groups


def enrich_items(
    client: MtopClient,
    cards: List[Dict[str, Any]],
    include_raw: bool,
    request_delay: float,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    total = len(cards)
    for index, card in enumerate(cards, 1):
        item_id = card["item_id"]
        logger.info(f"补全详情 {index}/{total}：{item_id}\n")
        response = client.request("mtop.taobao.idle.pc.detail", {"itemId": item_id})
        data = ensure_success("mtop.taobao.idle.pc.detail", response)
        items.append(normalize_detail(card, data, include_raw))
        if request_delay:
            time.sleep(request_delay)
    return items


def write_json(path: Path, meta: Dict[str, Any], items: List[Dict[str, Any]], groups: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            {
                "meta": meta,
                "groups": groups,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def write_markdown(path: Path, meta: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
    lines = [
        "# 闲鱼当前发布商品",
        "",
        f"- 账号：{meta.get('display_name') or meta.get('user_id')}",
        f"- 用户 ID：{meta.get('user_id')}",
        f"- 导出时间：{meta.get('exported_at')}",
        f"- 商品数量：{len(items)}",
        "",
    ]
    for index, item in enumerate(items, 1):
        title = item.get("title") or item.get("item_id")
        lines.extend(
            [
                f"## {index}. {title}",
                "",
                f"- 商品 ID：{item.get('item_id')}",
                f"- 价格：{item.get('price') or '-'}",
                f"- 原价：{item.get('original_price') or '-'}",
                f"- 状态：{item.get('status') or item.get('status_code') or '-'}",
                f"- 发布时间：{item.get('publish_time') or '-'}",
                f"- 浏览 / 想要 / 收藏：{item.get('browse_count') or 0} / {item.get('want_count') or 0} / {item.get('collect_count') or 0}",
                f"- 链接：{item.get('url')}",
            ]
        )
        labels = item.get("labels") or []
        if labels:
            lines.append(f"- 标签：{'、'.join(labels)}")
        if item.get("main_image"):
            lines.append(f"- 主图：{item.get('main_image')}")
        description = markdown_text(item.get("description"))
        if description:
            lines.extend(["", "### 描述", "", description])
        image_urls = item.get("image_urls") or []
        if image_urls:
            lines.extend(["", "### 图片", ""])
            lines.extend(f"- {url}" for url in image_urls)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出当前账号发布中的闲鱼商品")
    parser.add_argument("--cookie", help="登录后的完整 Cookie。默认读取 --cookie-file 或 XIANYU_COOKIE")
    parser.add_argument("--cookie-file", default=DEFAULT_COOKIE_FILE, help=f"Cookie 文件，默认 {DEFAULT_COOKIE_FILE}")
    parser.add_argument("--save-cookie-file", help="把刷新后的 Cookie 写入指定文件")
    parser.add_argument("--out", help=f"输出目录，默认写入 {DEFAULT_OUTPUT_ROOT}/xianyu_items_时间")
    parser.add_argument("--page-size", type=int, default=20, help="商品列表分页大小，默认 20")
    parser.add_argument("--no-detail", action="store_true", help="只导出列表字段，不逐个请求商品详情")
    parser.add_argument("--include-raw", action="store_true", help="在 JSON 中保留接口原始详情")
    parser.add_argument("--request-delay", type=float, default=0.2, help="详情接口请求间隔，默认 0.2 秒")
    parser.add_argument("--timeout", type=float, default=25.0, help="单次请求超时时间，默认 25 秒")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logger.remove()
    logger.add(lambda msg: print(msg, end="", flush=True), level="DEBUG" if args.debug else "INFO")

    cookie_text = read_cookie(args.cookie or "", args.cookie_file)
    if not cookie_text:
        raise RuntimeError("没有找到 Cookie。请先扫码登录，或传入 --cookie / --cookie-file")
    client = MtopClient(cookie_text, timeout=args.timeout)
    output_dir = Path(args.out or Path(DEFAULT_OUTPUT_ROOT) / f"xianyu_items_{now_label()}").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    profile = fetch_profile(client)
    display_name = first_text(profile.get("displayName"), profile.get("nick"), profile.get("nickName"))
    logger.info(f"开始导出账号 {display_name or client.user_id} 的当前发布商品\n")

    cards, groups = fetch_item_cards(client, args.page_size)
    if args.no_detail:
        items = []
        for card in cards:
            item = {key: value for key, value in card.items() if key != "list_raw"}
            item.setdefault("description", "")
            item.setdefault("image_urls", [item["main_image"]] if item.get("main_image") else [])
            items.append(item)
    else:
        items = enrich_items(client, cards, args.include_raw, args.request_delay)

    display_name = first_text(
        display_name,
        *[
            (item.get("seller") or {}).get("nick")
            for item in items
            if isinstance(item.get("seller"), dict)
        ],
    )
    exported_at = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S") if LOCAL_TZ else datetime.now().isoformat(timespec="seconds")
    meta = {
        "user_id": client.user_id,
        "display_name": display_name,
        "exported_at": exported_at,
        "count": len(items),
        "detail_enriched": not args.no_detail,
    }
    json_path = output_dir / "xianyu_items.json"
    markdown_path = output_dir / "xianyu_items.md"
    write_json(json_path, meta, items, groups)
    write_markdown(markdown_path, meta, items)

    save_cookie_file = args.save_cookie_file
    if save_cookie_file:
        cookie_path = Path(save_cookie_file).expanduser()
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text(client.cookie_text(), encoding="utf-8")
        try:
            cookie_path.chmod(0o600)
        except OSError:
            pass
        logger.info(f"已保存刷新后的 Cookie：{cookie_path}\n")

    logger.info(f"导出完成：{len(items)} 个商品\n")
    logger.info(f"JSON：{json_path}\n")
    logger.info(f"Markdown：{markdown_path}\n")


if __name__ == "__main__":
    main()
