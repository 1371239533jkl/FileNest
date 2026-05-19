"""
元数据提取器 - 提取图片EXIF、PDF属性等
"""
import os
import json
from datetime import datetime
from typing import Optional, Tuple

from utils.logger import logger


def extract_image_metadata(file_path: str) -> dict:
    """提取图片EXIF元数据"""
    metadata = {}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(file_path)
        metadata['width'] = img.width
        metadata['height'] = img.height

        exif_data = img.getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == 'DateTimeOriginal':
                    try:
                        metadata['photo_taken_time'] = datetime.strptime(
                            str(value), '%Y:%m:%d %H:%M:%S')
                    except (ValueError, TypeError):
                        pass
                elif tag == 'Model':
                    metadata['camera_model'] = str(value)[:100]
                elif tag == 'GPSInfo':
                    try:
                        gps = _parse_gps(value)
                        if gps:
                            metadata['gps_latitude'] = gps[0]
                            metadata['gps_longitude'] = gps[1]
                    except Exception:
                        pass
        img.close()
    except Exception as e:
        logger.debug(f"提取图片元数据失败: {file_path} - {e}")
    return metadata


def _parse_gps(gps_info) -> Optional[Tuple[float, float]]:
    """解析GPS信息"""
    try:
        def _to_degrees(value) -> float:
            d, m, s = value
            return float(d) + float(m) / 60.0 + float(s) / 3600.0

        lat = _to_degrees(gps_info[2])
        lon = _to_degrees(gps_info[4])

        if gps_info[1] == 'S':
            lat = -lat
        if gps_info[3] == 'W':
            lon = -lon
        return (lat, lon)
    except (KeyError, IndexError, TypeError):
        return None


def extract_pdf_metadata(file_path: str) -> dict:
    """提取PDF元数据"""
    metadata = {}
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        info = reader.metadata
        if info:
            if info.title:
                metadata['pdf_title'] = str(info.title)[:255]
            if info.author:
                metadata['pdf_author'] = str(info.author)[:100]
        metadata['pdf_pages'] = len(reader.pages)
    except Exception as e:
        logger.debug(f"提取PDF元数据失败: {file_path} - {e}")
    return metadata


def extract_video_metadata(file_path: str) -> dict:
    """提取视频基本信息（文件大小等，不依赖外部库）"""
    metadata = {}
    # 简单的基于文件大小估算，不引入重量级视频处理库
    try:
        size = os.path.getsize(file_path)
        metadata['extra_data'] = json.dumps({'file_size_bytes': size})
    except Exception as e:
        logger.debug(f"提取视频元数据失败: {file_path} - {e}")
    return metadata


def extract_metadata(file_path: str, file_type: str) -> dict:
    """根据文件类型自动选择提取方法"""
    if file_type == 'image':
        return extract_image_metadata(file_path)
    elif file_type == 'document':
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            return extract_pdf_metadata(file_path)
    elif file_type == 'video':
        return extract_video_metadata(file_path)
    return {}
