import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ChevronDown, ChevronUp, FileText, Brain, Link } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface EnhancedReportProps {
  report: any;
  thinkingProcess: any[];
  sourcesGathered: any[];
}

export const EnhancedReport: React.FC<EnhancedReportProps> = ({
  report,
  thinkingProcess,
  sourcesGathered,
}) => {
  const [showThinking, setShowThinking] = useState(false);
  const [showSources, setShowSources] = useState(false);

  return (
    <div className="space-y-4">
      {/* 主报告内容 */}
      <Card className="bg-neutral-900/50 border-neutral-700">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-400" />
            <CardTitle className="text-xl text-neutral-100">研究报告</CardTitle>
            <Badge variant="secondary" className="bg-blue-500/20 text-blue-300">
              已完成
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="prose prose-invert max-w-none">
            <ReactMarkdown className="text-neutral-200">
              {report?.enhanced_report || report?.content || '报告内容加载中...'}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>

      {/* 思考过程 - 默认折叠 */}
      {thinkingProcess && thinkingProcess.length > 0 && (
        <Card className="bg-neutral-900/30 border-neutral-700">
          <CardHeader>
            <div 
              className="flex items-center justify-between cursor-pointer"
              onClick={() => setShowThinking(!showThinking)}
            >
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                <CardTitle className="text-lg text-neutral-200">思考过程</CardTitle>
                <Badge variant="outline" className="text-xs">
                  {thinkingProcess.length} 个阶段
                </Badge>
              </div>
              {showThinking ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </CardHeader>
          {showThinking && (
            <CardContent>
              <div className="space-y-4">
                {thinkingProcess.map((stage, idx) => (
                  <div key={idx} className="border-l-2 border-purple-500/30 pl-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="secondary" className="bg-purple-500/20 text-purple-300">
                        {stage.stage || `阶段 ${idx + 1}`}
                      </Badge>
                      <span className="text-xs text-neutral-400">
                        {stage.timestamp}
                      </span>
                    </div>
                    <div className="text-sm text-neutral-300">
                      {stage.content && typeof stage.content === 'object' ? (
                        <pre className="whitespace-pre-wrap text-xs bg-neutral-800/50 p-2 rounded">
                          {JSON.stringify(stage.content, null, 2)}
                        </pre>
                      ) : (
                        <p>{stage.content || stage.summary}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* 数据源 - 默认折叠 */}
      {sourcesGathered && sourcesGathered.length > 0 && (
        <Card className="bg-neutral-900/30 border-neutral-700">
          <CardHeader>
            <div 
              className="flex items-center justify-between cursor-pointer"
              onClick={() => setShowSources(!showSources)}
            >
              <div className="flex items-center gap-2">
                <Link className="w-4 h-4 text-green-400" />
                <CardTitle className="text-lg text-neutral-200">引用数据源</CardTitle>
                <Badge variant="outline" className="text-xs">
                  {sourcesGathered.length} 个来源
                </Badge>
              </div>
              {showSources ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </CardHeader>
          {showSources && (
            <CardContent>
              <div className="space-y-3">
                {sourcesGathered.map((source, idx) => (
                  <div key={idx} className="border border-neutral-700 rounded p-3">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-medium text-neutral-200 text-sm">
                        {source.title || source.label || `来源 ${idx + 1}`}
                      </h4>
                      {source.url && (
                        <a 
                          href={source.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 text-xs"
                        >
                          查看原文
                        </a>
                      )}
                    </div>
                    {source.summary && (
                      <p className="text-xs text-neutral-400 mb-2">{source.summary}</p>
                    )}
                    {source.url && (
                      <p className="text-xs text-neutral-500 break-all">{source.url}</p>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
};
