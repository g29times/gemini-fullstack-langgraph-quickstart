#!/usr/bin/env python3
"""
博查 API 数据转换工具

将SerpAPI benchmark结果中的sources_details数据转换为指定格式
"""

import json
from typing import Dict, Any, List


def convert_sources_details(sources_details: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    将SerpAPI benchmark结果中的sources_details数据转换为指定格式
    
    Args:
        sources_details: 原始的sources_details数据列表
        
    Returns:
        转换后的数据列表，每个元素包含label、short_url、value字段
    """
    converted_data = []
    
    for source in sources_details:
        if isinstance(source, dict):
            # 检查是否已经是目标格式
            if all(key in source for key in ['label', 'short_url', 'value']):
                # 已经是目标格式，直接添加
                converted_data.append({
                    'label': str(source['label']),
                    'short_url': str(source['short_url']),
                    'value': str(source['value'])
                })
            else:
                # 需要转换的格式
                converted_item = {
                    'label': '',
                    'short_url': '',
                    'value': ''
                }
                
                # 尝试从不同字段提取label
                for label_field in ['title', 'label', 'name', 'text']:
                    if label_field in source and source[label_field]:
                        converted_item['label'] = str(source[label_field])
                        break
                
                # 尝试从不同字段提取URL
                for url_field in ['url', 'link', 'href', 'short_url', 'value']:
                    if url_field in source and source[url_field]:
                        url_value = str(source[url_field])
                        converted_item['short_url'] = url_value
                        converted_item['value'] = url_value
                        break
                
                # 如果没有找到合适的字段，使用默认值
                if not converted_item['label']:
                    converted_item['label'] = f"Source {len(converted_data) + 1}"
                
                if not converted_item['short_url']:
                    converted_item['short_url'] = '#'
                    converted_item['value'] = '#'
                
                converted_data.append(converted_item)
        else:
            # 如果source不是字典，创建默认项
            converted_data.append({
                'label': str(source) if source else f"Source {len(converted_data) + 1}",
                'short_url': '#',
                'value': '#'
            })
    
    return converted_data


def convert_benchmark_file(input_file: str, output_file: str = None) -> Dict[str, Any]:
    """
    转换整个benchmark文件中的sources_details数据
    
    Args:
        input_file: 输入的benchmark JSON文件路径
        output_file: 输出文件路径（可选）
        
    Returns:
        转换后的完整数据
    """
    # 读取原始文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 转换每个结果中的sources_details
    if 'results' in data:
        for result in data['results']:
            if 'sources_details' in result:
                result['sources_details'] = convert_sources_details(result['sources_details'])
    
    # 如果指定了输出文件，保存转换后的数据
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"转换后的数据已保存到: {output_file}")
    
    return data


def demo_conversion():
    """
    演示数据转换功能
    """
    print("数据转换演示")
    print("=" * 50)
    
    # 示例原始数据
    sample_sources = [
        {
            "label": "2025年第一次装修改造项目中选结果公告",
            "short_url": "https://kfqgw.beijing.gov.cn/zwgkkfq/tzgg/202503/t20250325_4043846.html",
            "value": "https://kfqgw.beijing.gov.cn/zwgkkfq/tzgg/202503/t20250325_4043846.html"
        },
        {
            "title": "北京大学项目公告",
            "url": "https://example.com/project"
        },
        {
            "name": "修缮工程项目",
            "link": "https://example.com/repair"
        }
    ]
    
    print("原始数据:")
    print(json.dumps(sample_sources, ensure_ascii=False, indent=2))
    
    print("\n转换后数据:")
    converted = convert_sources_details(sample_sources)
    print(json.dumps(converted, ensure_ascii=False, indent=2))
    
    print("\n转换完成！")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            # 运行演示
            demo_conversion()
        elif sys.argv[1] == "--convert":
            # 转换文件
            if len(sys.argv) < 3:
                print("用法: python data_converter.py --convert <输入文件> [输出文件]")
                sys.exit(1)
            
            input_file = sys.argv[2]
            output_file = sys.argv[3] if len(sys.argv) > 3 else None
            
            try:
                convert_benchmark_file(input_file, output_file)
                print("文件转换完成！")
            except Exception as e:
                print(f"转换失败: {e}")
                sys.exit(1)
        else:
            print("未知参数")
            print("用法:")
            print("  python data_converter.py --demo                    # 运行演示")
            print("  python data_converter.py --convert <输入文件> [输出文件]  # 转换文件")
    else:
        print("数据转换工具")
        print("用法:")
        print("  python data_converter.py --demo                    # 运行演示")
        print("  python data_converter.py --convert <输入文件> [输出文件]  # 转换文件")
        print("\n示例:")
        print("  python data_converter.py --demo")
        print("  python data_converter.py --convert serpapi_benchmark_results_20250909_210527.json converted_results.json")