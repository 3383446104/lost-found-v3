# app/validators.py
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