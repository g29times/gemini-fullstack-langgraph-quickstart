import React, { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ChevronDown, ChevronUp, CheckCircle } from 'lucide-react';

interface ResearchPlan {
  research_objectives: string[];
  planned_queries: string[];
  research_methodology: string;
  expected_outcomes: string;
  estimated_time: string;
  potential_challenges: string[];
  alternative_approaches: string[];
}

interface CollapsedResearchPlanProps {
  researchPlan: ResearchPlan;
}

export const CollapsedResearchPlan: React.FC<CollapsedResearchPlanProps> = ({
  researchPlan,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getPreviewText = () => {
    const objectives = researchPlan.research_objectives?.slice(0, 2).join('，') || '';
    const methodology = researchPlan.research_methodology || '';
    return `${objectives}${methodology ? `。研究方法：${methodology.substring(0, 100)}` : ''}`;
  };

  return (
    <Card className="mb-4 bg-green-900/20 border-green-500/30">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            <Badge variant="secondary" className="bg-green-500/20 text-green-300">
              已批准研究计划
            </Badge>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>

        {!isExpanded ? (
          <div className="text-sm text-neutral-300">
            <p className="line-clamp-3">
              {getPreviewText()}
              {getPreviewText().length > 200 && '...'}
            </p>
            <button
              onClick={() => setIsExpanded(true)}
              className="text-blue-400 hover:text-blue-300 text-xs mt-1"
            >
              展开查看完整计划
            </button>
          </div>
        ) : (
          <div className="space-y-3 text-sm">
            <div>
              <h4 className="font-medium text-neutral-200 mb-1">研究目标</h4>
              <ul className="list-disc list-inside text-neutral-300 space-y-1">
                {researchPlan.research_objectives?.map((obj, idx) => (
                  <li key={idx}>{obj}</li>
                ))}
              </ul>
            </div>

            <div>
              <h4 className="font-medium text-neutral-200 mb-1">计划查询</h4>
              <ul className="list-disc list-inside text-neutral-300 space-y-1">
                {researchPlan.planned_queries?.map((query, idx) => (
                  <li key={idx}>{query}</li>
                ))}
              </ul>
            </div>

            <div>
              <h4 className="font-medium text-neutral-200 mb-1">研究方法</h4>
              <p className="text-neutral-300">{researchPlan.research_methodology}</p>
            </div>

            <div className="flex gap-4">
              <div>
                <h4 className="font-medium text-neutral-200 mb-1">预期成果</h4>
                <p className="text-neutral-300">{researchPlan.expected_outcomes}</p>
              </div>
              <div>
                <h4 className="font-medium text-neutral-200 mb-1">预估时间</h4>
                <p className="text-neutral-300">{researchPlan.estimated_time}</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
