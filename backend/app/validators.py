# app/validators.py
import datetime
import re


def validate_item_title(title):
    """验证物品标题：2-50字符"""
    if not title:
        return False, '标题不能为空'
    if len(title) < 2 or len(title) > 50:
        return False, '标题长度应在2-50字符之间'
    return True, ''


def validate_contact(contact):
    """验证联系方式：最长50字符（选填）"""
    if not contact:
        return True, ''
    if len(contact) > 50:
        return False, '联系方式不能超过50字符'
    return True, ''


def validate_structured_field(value, max_len, name):
    """选填结构化字段（v3.7.0）：空 → 合法；超过 max_len → 不合法。"""
    if not value:
        return True, ''
    if len(value) > max_len:
        return False, f'{name}不能超过{max_len}字符'
    return True, ''


def validate_occurred_at(value):
    """发生时间（选填，v3.7.0）：``YYYY-MM-DD`` 或 ``YYYY-MM-DD HH:MM[:SS]``。"""
    if not value:
        return True, ''
    try:
        datetime.datetime.fromisoformat(str(value).strip().replace(' ', 'T'))
    except ValueError:
        return False, '发生时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM'
    return True, ''