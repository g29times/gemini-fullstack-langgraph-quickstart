import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Brain, Lightbulb, Target, ArrowRight, CheckCircle } from 'lucide-react';

interface ThinkingStage {
  stage: string;
  timestamp: string;
  content: {
    stage_name: string;
    overview?: string;
    key_components?: string[];
    research_directions?: string[];
    priorities?: string[];
    key_insights?: string[];
    information_gaps?: string[];
    connections_found?: string[];
    areas_for_deepening?: string[];
    final_insights?: string[];
    knowledge_structure?: Record<string, string[]>;
    key_conclusions?: string[];
  };
}

interface ThinkingProcessProps {
  thinkingProcess: ThinkingStage[];
  currentStage?: string;
}

export const ThinkingProcess: React.FC<ThinkingProcessProps> = ({
  thinkingProcess,
  currentStage = "startup"
}) => {
  const getStageIcon = (stage: string) => {
    switch (stage) {
      case 'startup':
        return <Target className="w-5 h-5 text-blue-400" />;
      case 'middle':
        return <Brain className="w-5 h-5 text-purple-400" />;
      case 'finalization':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      default:
        return <Lightbulb className="w-5 h-5 text-yellow-400" />;
    }
  };

  const getStageColor = (stage: string) => {
    switch (stage) {
      case 'startup':
        return 'border-blue-500 bg-blue-900/20';
      case 'middle':
        return 'border-purple-500 bg-purple-900/20';
      case 'finalization':
        return 'border-green-500 bg-green-900/20';
      default:
        return 'border-yellow-500 bg-yellow-900/20';
    }
  };

  const renderStartupStage = (content: ThinkingStage['content']) => (
    <div className="space-y-4">
      {content.overview && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">研究概述</h4>
          <p className="text-neutral-300 text-sm">{content.overview}</p>
        </div>
      )}
      
      {content.key_components && content.key_components.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">核心要素</h4>
          <div className="flex flex-wrap gap-2">
            {content.key_components.map((component, index) => (
              <Badge key={index} variant="secondary" className="bg-blue-800 text-blue-100">
                {component}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {content.research_directions && content.research_directions.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">研究方向</h4>
          <ul className="space-y-1">
            {content.research_directions.map((direction, index) => (
              <li key={index} className="text-neutral-300 text-sm flex items-start gap-2">
                <ArrowRight className="w-3 h-3 mt-1 text-blue-400 flex-shrink-0" />
                {direction}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  const renderMiddleStage = (content: ThinkingStage['content']) => (
    <div className="space-y-4">
      {content.key_insights && content.key_insights.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-yellow-400" />
            关键洞察
          </h4>
          <ul className="space-y-1">
            {content.key_insights.map((insight, index) => (
              <li key={index} className="text-neutral-300 text-sm">• {insight}</li>
            ))}
          </ul>
        </div>
      )}

      {content.connections_found && content.connections_found.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">发现的关联</h4>
          <ul className="space-y-1">
            {content.connections_found.map((connection, index) => (
              <li key={index} className="text-neutral-300 text-sm">🔗 {connection}</li>
            ))}
          </ul>
        </div>
      )}

      {content.information_gaps && content.information_gaps.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">信息缺口</h4>
          <ul className="space-y-1">
            {content.information_gaps.map((gap, index) => (
              <li key={index} className="text-neutral-400 text-sm">⚠️ {gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  const renderFinalizationStage = (content: ThinkingStage['content']) => (
    <div className="space-y-4">
      {content.final_insights && content.final_insights.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            最终洞察
          </h4>
          <ul className="space-y-1">
            {content.final_insights.map((insight, index) => (
              <li key={index} className="text-neutral-300 text-sm">✨ {insight}</li>
            ))}
          </ul>
        </div>
      )}

      {content.knowledge_structure && Object.keys(content.knowledge_structure).length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">知识结构</h4>
          <div className="space-y-2">
            {Object.entries(content.knowledge_structure).map(([topic, points], index) => (
              <div key={index} className="bg-neutral-800 p-3 rounded-md">
                <h5 className="font-medium text-neutral-200 mb-1">{topic}</h5>
                <ul className="space-y-1">
                  {points.map((point, pointIndex) => (
                    <li key={pointIndex} className="text-neutral-400 text-sm">• {point}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {content.key_conclusions && content.key_conclusions.length > 0 && (
        <div>
          <h4 className="font-semibold text-neutral-200 mb-2">关键结论</h4>
          <ul className="space-y-1">
            {content.key_conclusions.map((conclusion, index) => (
              <li key={index} className="text-neutral-300 text-sm">🎯 {conclusion}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="text-center mb-6">
        <h3 className="text-lg font-bold text-neutral-100 flex items-center justify-center gap-2">
          <Brain className="w-5 h-5 text-purple-400" />
          研究思考过程
        </h3>
        <p className="text-neutral-400 text-sm">深度研究的结构化思考阶段</p>
      </div>

      {thinkingProcess.map((stage, index) => (
        <Card key={index} className={`bg-neutral-900 ${getStageColor(stage.stage)}`}>
          <CardHeader className="pb-3">
            <CardTitle className="text-neutral-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {getStageIcon(stage.stage)}
                {stage.content.stage_name}
              </div>
              <Badge variant="outline" className="text-xs">
                {stage.timestamp}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {stage.stage === 'startup' && renderStartupStage(stage.content)}
            {stage.stage === 'middle' && renderMiddleStage(stage.content)}
            {stage.stage === 'finalization' && renderFinalizationStage(stage.content)}
          </CardContent>
        </Card>
      ))}

      {thinkingProcess.length === 0 && (
        <Card className="bg-neutral-900 border-neutral-700">
          <CardContent className="text-center py-8">
            <Brain className="w-12 h-12 text-neutral-600 mx-auto mb-4" />
            <p className="text-neutral-400">思考过程将在研究开始后显示...</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
