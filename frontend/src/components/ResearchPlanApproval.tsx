import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { CheckCircle, Clock, Edit, ArrowRight } from 'lucide-react';

interface ResearchPlan {
  research_objectives: string[];
  planned_queries: string[];
  research_methodology: string;
  expected_outcomes: string;
  estimated_time: string;
  potential_challenges: string[];
  alternative_approaches: string[];
}

interface ResearchPlanApprovalProps {
  researchPlan: ResearchPlan;
  onApprove: (modifications?: string) => void;
  onModify: (modifications: string) => void;
  isLoading?: boolean;
}

export const ResearchPlanApproval: React.FC<ResearchPlanApprovalProps> = ({
  researchPlan,
  onApprove,
  onModify,
  isLoading = false,
}) => {
  const [showModifications, setShowModifications] = useState(false);
  const [modifications, setModifications] = useState('');

  const handleApprove = () => {
    onApprove(modifications.trim() || undefined);
  };

  const handleModify = () => {
    if (modifications.trim()) {
      onModify(modifications.trim());
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-neutral-100 flex items-center justify-center gap-2">
          <Clock className="w-6 h-6 text-blue-400" />
          研究方案预览
        </h2>
        <p className="text-neutral-400">请审核以下研究计划，您可以直接批准或提出修改建议</p>
      </div>

      <div className="grid gap-6">
        {/* Research Objectives */}
        <Card className="bg-neutral-900 border-neutral-700">
          <CardHeader>
            <CardTitle className="text-neutral-100 flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              研究目标
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {researchPlan.research_objectives.map((objective, index) => (
                <li key={index} className="flex items-start gap-2 text-neutral-300">
                  <span className="text-blue-400 font-semibold">{index + 1}.</span>
                  {objective}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Research Methodology */}
        <Card className="bg-neutral-900 border-neutral-700">
          <CardHeader>
            <CardTitle className="text-neutral-100">研究方法</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-neutral-300">{researchPlan.research_methodology}</p>
          </CardContent>
        </Card>

        {/* Planned Queries */}
        <Card className="bg-neutral-900 border-neutral-700">
          <CardHeader>
            <CardTitle className="text-neutral-100">计划搜索查询</CardTitle>
            <CardDescription>将执行以下搜索查询来收集信息</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {researchPlan.planned_queries.map((query, index) => (
                <Badge key={index} variant="secondary" className="bg-blue-900 text-blue-100">
                  {query}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Expected Outcomes & Time */}
        <div className="grid md:grid-cols-2 gap-6">
          <Card className="bg-neutral-900 border-neutral-700">
            <CardHeader>
              <CardTitle className="text-neutral-100">预期成果</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-neutral-300">{researchPlan.expected_outcomes}</p>
            </CardContent>
          </Card>

          <Card className="bg-neutral-900 border-neutral-700">
            <CardHeader>
              <CardTitle className="text-neutral-100">预估时间</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-neutral-300 font-semibold">{researchPlan.estimated_time}</p>
            </CardContent>
          </Card>
        </div>

        {/* Challenges & Alternatives */}
        <div className="grid md:grid-cols-2 gap-6">
          <Card className="bg-neutral-900 border-neutral-700">
            <CardHeader>
              <CardTitle className="text-neutral-100 text-sm">潜在挑战</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm">
                {researchPlan.potential_challenges.map((challenge, index) => (
                  <li key={index} className="text-neutral-400">• {challenge}</li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card className="bg-neutral-900 border-neutral-700">
            <CardHeader>
              <CardTitle className="text-neutral-100 text-sm">备选方案</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm">
                {researchPlan.alternative_approaches.map((approach, index) => (
                  <li key={index} className="text-neutral-400">• {approach}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>

        {/* Modification Input */}
        {showModifications && (
          <Card className="bg-neutral-900 border-neutral-700">
            <CardHeader>
              <CardTitle className="text-neutral-100 flex items-center gap-2">
                <Edit className="w-5 h-5 text-orange-400" />
                修改建议
              </CardTitle>
              <CardDescription>请描述您希望如何调整研究计划</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                placeholder="例如：请增加对竞争对手分析的内容，重点关注最新的市场趋势..."
                value={modifications}
                onChange={(e) => setModifications(e.target.value)}
                className="min-h-[100px] bg-neutral-800 border-neutral-600 text-neutral-100"
              />
            </CardContent>
          </Card>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Button
            onClick={handleApprove}
            disabled={isLoading}
            className="bg-green-600 hover:bg-green-700 text-white flex items-center gap-2"
          >
            <CheckCircle className="w-4 h-4" />
            {modifications.trim() ? '批准并应用修改' : '批准研究计划'}
            <ArrowRight className="w-4 h-4" />
          </Button>

          <Button
            onClick={() => setShowModifications(!showModifications)}
            variant="outline"
            className="border-orange-600 text-orange-400 hover:bg-orange-600 hover:text-white flex items-center gap-2"
          >
            <Edit className="w-4 h-4" />
            {showModifications ? '取消修改' : '提出修改'}
          </Button>
        </div>
      </div>
    </div>
  );
};
