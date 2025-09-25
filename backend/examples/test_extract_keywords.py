#!/usr/bin/env python3
"""
测试 QueryManager._extract_recommend_keywords 方法的关键词提取功能
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch

# 添加项目路径到 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from agent.graph import QueryManager
from agent.configuration import Configuration
from agent.state import OverallState


class TestExtractProjectKeywords(unittest.TestCase):
    """测试关键词提取功能"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建模拟的配置和状态
        self.mock_config = Mock(spec=Configuration)
        self.mock_state = Mock(spec=OverallState)
        
        # 创建 QueryManager 实例
        with patch.object(QueryManager, '_get_query_count', return_value=4):
            self.query_manager = QueryManager(self.mock_state, self.mock_config)
    
    def test_extract_keywords_from_real_projects(self):
        """测试从真实项目数据中提取关键词"""
        # 模拟真实的用户项目上下文 "华西大区西安CCBD公寓项目\n网大科技有限公司写字楼"
        user_projects_context = (
            "•华西大区·西安酒店精装设计项目(建设单位：浙江青山湖科研创新基地投资有限公司)\n"
            "•网大科技有限公司写字楼(乌鲁木齐隆瑞弘光房地产开发有限公司)\n"
            "•宋园路20号修缮项目(中共上海市委社会工作部)\n"
            "•深圳市登喜路大酒店集团项目(登喜路集团有限公司)\n"
            "•平安中心大厦写字楼(平安国际金融)\n"
            "•海湾户外运动场(上海市奉贤区体育局)"
        )
        # [
            # {
            #     "title": "华西大区·西安酒店精装设计项目",
            #     "customer": "建设单位：浙江青山湖科研创新基地投资有限公司"
            # },
            # {
            #     "title": "测试归口",
            #     "customer": "佳县林业局"
            # },
            # {
            #     "title": "网大科技有限公司写字楼",
            #     "customer": "乌鲁木齐隆瑞弘光房地产开发有限公司"
            # },
            # {
            #     "title": "宋园路20号修缮项目",
            #     "customer": "中共上海市委社会工作部"
            # },
            # {
            #     "title": "硬装--已加入项目的物料状态定期更新规则",
            #     "customer": "岚皋县住房和城乡建设局"
            # },
            # {
            #     "title": "深圳市登喜路大酒店集团项目",
            #     "customer": "登喜路集团有限公司"
            # },
            # {
            #     "title": "(专用勿乱动)IdeaFusion国际酒店项目",
            #     "customer": "犀照科技"
            # },
            # {
            #     "title": "平安中心大厦写字楼",
            #     "customer": "平安国际金融"
            # },
            # {
            #     "title": "海湾户外运动场",
            #     "customer": "上海市奉贤区体育局"
            # },
            # {
            #     "title": "供应商确认物料",
            #     "customer": "首都师范大学"
            # }
        # ]
        
        # 调用关键词提取方法
        keywords = self.query_manager._extract_recommend_keywords(user_projects_context)
        
        # 打印结果用于调试
        print(f"\n提取到的关键词: {keywords}")
        
        # 验证结果
        self.assertIsInstance(keywords, list)
        self.assertLessEqual(len(keywords), 15)  # 最多5个关键词
        
        # 验证应该包含的关键词
        expected_keywords = ['华西大区', '西安', 'CCBD', '网大科技', '写字楼', 
                           '深圳市', '登喜路', '大酒店', '集团', '平安中心', 
                           '大厦', 'IdeaFusion', '国际酒店', '犀照科技']
        
        # 至少应该提取到一些有价值的关键词
        self.assertGreater(len(keywords), 0, "应该提取到至少一个关键词")
        
        # 验证不应该包含停用词
        stop_words = {'项目', '有限', '股份', '建设', '工程', '采购', '招标', '公告', '测试', '演示'}
        for keyword in keywords:
            self.assertNotIn(keyword, stop_words, f"关键词 '{keyword}' 不应该是停用词")
        
        # 验证关键词长度
        for keyword in keywords:
            if keyword.isalpha() and all(ord(c) < 128 for c in keyword):  # 英文单词
                self.assertGreaterEqual(len(keyword), 3, f"英文关键词 '{keyword}' 长度应该 >= 3")
            else:  # 中文词汇
                self.assertGreaterEqual(len(keyword), 2, f"中文关键词 '{keyword}' 长度应该 >= 2")
    
    def test_extract_keywords_empty_input(self):
        """测试空输入的情况"""
        keywords = self.query_manager._extract_recommend_keywords("")
        self.assertEqual(keywords, [])
        
        keywords = self.query_manager._extract_recommend_keywords(None)
        self.assertEqual(keywords, [])
    
    def test_extract_keywords_no_bullet_points(self):
        """测试没有项目符号的输入"""
        context = "华西大区西安CCBD公寓项目\n网大科技有限公司写字楼"
        keywords = self.query_manager._extract_recommend_keywords(context)
        self.assertEqual(keywords, [], "没有 '•' 符号的行应该被忽略")
    
    def test_extract_keywords_only_stop_words(self):
        """测试只包含停用词的情况"""
        context = "• 项目建设工程采购招标公告 (客户: 有限股份公司)"
        keywords = self.query_manager._extract_recommend_keywords(context)
        self.assertEqual(keywords, [], "只有停用词的项目应该返回空列表")
    
    def test_extract_keywords_mixed_languages(self):
        """测试中英文混合的项目名称"""
        context = """• Microsoft Office 365企业版部署项目 (客户: 微软中国)
        • Apple Store 零售店装修设计 (客户: 苹果公司)
        • Google Cloud 数据中心建设 (客户: 谷歌)"""
        
        keywords = self.query_manager._extract_recommend_keywords(context)
        
        print(f"\n混合语言关键词: {keywords}")
        
        # 应该包含英文和中文关键词
        has_english = any(keyword.isalpha() and all(ord(c) < 128 for c in keyword) for keyword in keywords)
        has_chinese = any(any('\u4e00' <= c <= '\u9fff' for c in keyword) for keyword in keywords)
        
        self.assertTrue(has_english or has_chinese, "应该提取到英文或中文关键词")
    
    def test_extract_keywords_deduplication(self):
        """测试关键词去重功能"""
        context = """• 华西大区项目A (客户: 华西大区)
        • 华西大区项目B (客户: 华西大区)
        • 西安CCBD项目C (客户: 西安CCBD)"""
        
        keywords = self.query_manager._extract_recommend_keywords(context)
        
        # 验证去重效果
        unique_keywords = list(set(keywords))
        self.assertEqual(len(keywords), len(unique_keywords), "关键词应该已经去重")
    
    def test_extract_keywords_length_limit(self):
        """测试关键词数量限制"""
        # 创建包含很多关键词的长项目列表
        context = """• 华西大区西安CCBD公寓项目 (客户: 华西大区)
        • 网大科技有限公司写字楼 (客户: 网大科技)
        • 深圳市登喜路大酒店集团 (客户: 登喜路集团)
        • 平安中心大厦写字楼 (客户: 平安国际金融)
        • IdeaFusion国际酒店项目 (客户: 犀照科技)
        • 万科地产住宅项目 (客户: 万科集团)
        • 恒大集团商业综合体 (客户: 恒大地产)
        • 碧桂园花园洋房项目 (客户: 碧桂园集团)"""
        
        keywords = self.query_manager._extract_recommend_keywords(context)
        
        # 验证关键词数量不超过15个
        self.assertLessEqual(len(keywords), 15, "关键词数量应该不超过15个")


def run_detailed_test():
    """运行详细的测试并打印分析结果"""
    print("=" * 60)
    print("关键词提取功能详细测试")
    print("=" * 60)
    
    # 创建测试实例
    test_instance = TestExtractProjectKeywords()
    test_instance.setUp()
    
    # 测试真实项目数据
    print("\n1. 测试真实项目数据:")
    test_instance.test_extract_keywords_from_real_projects()
    
    # 测试混合语言
    # print("\n2. 测试中英文混合:")
    # test_instance.test_extract_keywords_mixed_languages()
    
    # # 分析每个项目的关键词提取
    # print("\n3. 逐项目分析:")
    # projects = [
    #     "华西大区·西安CCBD公寓项目公寓户内及公寓公区精装设计项目",
    #     "网大科技有限公司写字楼", 
    #     "深圳市登喜路大酒店集团项目",
    #     "平安中心大厦写字楼",
    #     "(专用勿乱动)IdeaFusion国际酒店项目"
    # ]
    
    # for project in projects:
    #     context = f"• {project} (客户: 测试客户)"
    #     keywords = test_instance.query_manager._extract_recommend_keywords(context)
    #     print(f"  项目: {project}")
    #     print(f"  关键词: {keywords}")
    #     print()


if __name__ == "__main__":
    # 运行详细测试
    run_detailed_test()
    
    print("\n" + "=" * 60)
    print("运行单元测试")
    print("=" * 60)
    
    # 运行单元测试
    unittest.main(verbosity=2)
