import re

def clean_markdown_tables(text: str) -> str:
    """
    清理文本中的所有Markdown表格，修复多余分隔符、合并断行单元格。
    """
    lines = text.strip().splitlines()
    cleaned_lines = []
    buffer = []
    in_table = False

    for line in lines:
        if "|" in line:  # 可能是表格行
            in_table = True
            buffer.append(line.strip())
        else:
            if in_table:  # 表格结束，处理缓存的表格
                cleaned_lines.extend(_fix_table(buffer))
                buffer = []
                in_table = False
            cleaned_lines.append(line)
    
    if buffer:  # 最后还有未处理的表格
        cleaned_lines.extend(_fix_table(buffer))

    return "\n".join(cleaned_lines)


def _fix_table(table_lines):
    """
    修复单个Markdown表格
    """
    # 去掉空行和无效的行
    table_lines = [l for l in table_lines if l.strip() and l.strip() != "|"]

    # 拆分单元格
    rows = []
    for line in table_lines:
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p != ""]  # 去掉多余空白单元格
        if parts:
            rows.append(parts)

    if not rows:
        return []

    # 确定列数：取所有行中最大的列数
    max_cols = max(len(r) for r in rows)

    # 标准化行（补齐列数）
    fixed_rows = []
    buffer = []
    for row in rows:
        buffer.extend(row)
        if len(buffer) >= max_cols:
            fixed_rows.append(buffer[:max_cols])
            buffer = buffer[max_cols:]  # 剩余的留待下一次补齐

    # 构造表头和分隔符
    header = fixed_rows[0]
    separator = ["-" * max(4, len(h)) for h in header]  # 至少4个"-"
    
    # 拼接回Markdown表格
    fixed = []
    fixed.append("| " + " | ".join(header) + " |")
    fixed.append("| " + " | ".join(separator) + " |")
    for row in fixed_rows[1:]:
        fixed.append("| " + " | ".join(row) + " |")

    return fixed

if __name__ == "__main__":
    with open("input.md", "r", encoding="utf-8") as f:
        text = f.read()
    cleaned_text = clean_markdown_tables(text)
    with open("output.md", "w", encoding="utf-8") as f:
        f.write(cleaned_text)
