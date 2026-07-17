import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Link } from 'react-router-dom';
import { apiRequest, API_ENDPOINTS } from '../config/api';

interface Citation {
  chunk_id: number;
  quote: string;
  source_url?: string | null;
  deep_link?: string | null;
  meeting_title?: string | null;
  meeting_date?: string | null;
  item_number?: string | null;
  page?: number | null;
}

interface ChatApiResponse {
  response: string;
  success: boolean;
  intent?: string;
  status?: 'answered' | 'partial' | 'refused';
  citations?: Citation[];
  unsupported_claims?: string[];
  error?: string;
}

interface ChatMessage {
  id: number;
  text: string;
  isUser: boolean;
  timestamp: Date;
  status?: 'answered' | 'partial' | 'refused' | 'error';
  citations?: Citation[];
  unsupportedClaims?: string[];
}

interface MarkdownLinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  href?: string;
  children?: React.ReactNode;
}

interface MarkdownElementProps extends React.HTMLAttributes<HTMLElement> {
  children?: React.ReactNode;
}

const MarkdownComponents = {
  a: ({ href, children, ...props }: MarkdownLinkProps) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 hover:text-blue-800 underline font-medium"
      {...props}
    >
      {children}
    </a>
  ),
  p: ({ children, ...props }: MarkdownElementProps) => (
    <p className="mb-2 last:mb-0" {...props}>
      {children}
    </p>
  ),
  ul: ({ children, ...props }: MarkdownElementProps) => (
    <ul className="list-disc list-inside mb-2 ml-2" {...props}>
      {children}
    </ul>
  ),
  li: ({ children, ...props }: MarkdownElementProps) => (
    <li className="mb-1" {...props}>
      {children}
    </li>
  ),
  strong: ({ children, ...props }: MarkdownElementProps) => (
    <strong className="font-semibold" {...props}>
      {children}
    </strong>
  ),
};

/**
 * Replace [c:ID] markers with superscript reference numbers keyed to
 * the message's citation list.
 */
const formatWithCitations = (
  text: string,
  citations: Citation[]
): { markdown: string; ordered: Citation[] } => {
  const ordered: Citation[] = [];
  const markdown = text.replace(/\[c:(\d+)\]/g, (_match, idRaw) => {
    const chunkId = Number(idRaw);
    let index = ordered.findIndex((c) => c.chunk_id === chunkId);
    if (index === -1) {
      const citation = citations.find((c) => c.chunk_id === chunkId);
      if (!citation) return '';
      ordered.push(citation);
      index = ordered.length - 1;
    }
    return `[^${index + 1}]`;
  });
  return { markdown: markdown.replace(/\[\^(\d+)\]/g, ' **[$1]**'), ordered };
};

const CitationList: React.FC<{ citations: Citation[] }> = ({ citations }) => {
  if (!citations.length) return null;
  return (
    <ol className="mt-2 border-t border-gray-200 pt-2 space-y-1">
      {citations.map((citation, i) => (
        <li key={`${citation.chunk_id}-${i}`} className="text-xs text-gray-600">
          <span className="font-semibold">[{i + 1}]</span>{' '}
          {citation.meeting_title && (
            <span>
              {citation.meeting_title}
              {citation.meeting_date && ` (${citation.meeting_date})`}
              {citation.item_number && `, item ${citation.item_number}`}
              {' — '}
            </span>
          )}
          {citation.deep_link && (
            <Link to={citation.deep_link} className="text-blue-600 underline">
              view item
            </Link>
          )}
          {citation.deep_link && citation.source_url && ' · '}
          {citation.source_url && (
            <a
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline"
            >
              source{citation.page ? ` p.${citation.page}` : ''} ↗
            </a>
          )}
        </li>
      ))}
    </ol>
  );
};

const WELCOME =
  "Hi! I answer questions about **Tulsa city government** using the " +
  'official meeting record — every claim comes with a citation you can ' +
  'check. If the records don’t support an answer, I’ll say so ' +
  'instead of guessing.\n\nTry asking about recent agenda items, votes, ' +
  'or who represents your address.';

export const ChatbotWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 1, text: WELCOME, isUser: false, timestamp: new Date() },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (isOpen && inputRef.current) inputRef.current.focus();
  }, [isOpen]);

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now(),
      text: inputValue,
      isUser: true,
      timestamp: new Date(),
    };
    const messageText = inputValue;
    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsTyping(true);

    try {
      const conversationHistory = messages.map((msg) => ({
        text: msg.text,
        sender: msg.isUser ? 'user' : 'bot',
      }));

      const response = await apiRequest<ChatApiResponse>(API_ENDPOINTS.chatbot, {
        method: 'POST',
        body: JSON.stringify({
          message: messageText,
          conversation_history: conversationHistory,
        }),
      });

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          text: response.response,
          isUser: false,
          timestamp: new Date(),
          status: response.status || 'answered',
          citations: response.citations || [],
          unsupportedClaims: response.unsupported_claims || [],
        },
      ]);
    } catch {
      // Honest failure — no canned fake answers
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          text:
            "I couldn't reach the server. The meeting records are still " +
            'browsable on the [Meetings page](/meetings).',
          isUser: false,
          timestamp: new Date(),
          status: 'error',
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const renderBotMessage = (message: ChatMessage) => {
    const { markdown, ordered } = formatWithCitations(
      message.text,
      message.citations || []
    );
    return (
      <>
        {message.status === 'refused' && (
          <p className="text-xs font-semibold text-amber-700 mb-1">
            No verified answer available
          </p>
        )}
        <ReactMarkdown
          components={MarkdownComponents}
          className="prose prose-sm max-w-none text-brand-dark-blue"
        >
          {markdown}
        </ReactMarkdown>
        <CitationList citations={ordered.length ? ordered : message.citations || []} />
        {(message.unsupportedClaims || []).length > 0 && (
          <p className="mt-2 text-xs text-amber-700">
            {message.unsupportedClaims!.length} unverified claim
            {message.unsupportedClaims!.length > 1 ? 's were' : ' was'} removed
            from this answer.
          </p>
        )}
      </>
    );
  };

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {isOpen && (
        <div className="mb-4 w-100 h-[32rem] bg-white rounded-lg shadow-xl border border-gray-200 flex flex-col">
          <div className="bg-brand-dark-blue text-white p-4 rounded-t-lg">
            <div className="flex items-start justify-between">
              <div>
                <h4 className="font-semibold text-white">CivicSpark Assistant</h4>
                <p className="font-semibold text-xs text-brand-yellow">
                  Cited answers from the Tulsa meeting record
                </p>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="text-white hover:text-brand-red transition-colors focus:outline-none"
                aria-label="Close chat"
              >
                <span className="text-xl">✕</span>
              </button>
            </div>
          </div>

          <div className="flex-1 p-4 overflow-y-auto bg-gray-50">
            <div className="space-y-4">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.isUser ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                      message.isUser
                        ? 'bg-brand-medium-blue text-white'
                        : message.status === 'refused' || message.status === 'error'
                          ? 'bg-amber-50 text-gray-800 border border-amber-200'
                          : 'bg-white text-gray-800 border border-gray-200'
                    }`}
                  >
                    <div className="text-sm">
                      {message.isUser ? message.text : renderBotMessage(message)}
                    </div>
                    <p
                      className={`text-xs mt-2 ${
                        message.isUser ? 'text-primary-100' : 'text-gray-500'
                      }`}
                    >
                      {message.timestamp.toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="flex justify-start">
                  <div className="bg-white text-gray-800 border border-gray-200 px-4 py-2 rounded-lg">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '0.1s' }}
                      ></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: '0.2s' }}
                      ></div>
                    </div>
                  </div>
                </div>
              )}
            </div>
            <div ref={messagesEndRef} />
          </div>

          <div className="p-4 border-t border-gray-200 bg-white rounded-b-lg">
            <div className="flex space-x-2">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder="Ask about Tulsa city government..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-yellow focus:border-transparent text-sm"
              />
              <button
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || isTyping}
                className="flex items-center justify-center px-3 py-1 bg-brand-dark-blue text-white rounded-lg text-xs font-semibold transition-colors hover:bg-brand-red hover:text-white disabled:opacity-50 disabled:cursor-not-allowed min-w-[40px]"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}

      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="bg-brand-red border-4 border-brand-yellow text-white p-4 rounded-full shadow-lg transition-colors hover:bg-brand-red focus:outline-none"
          aria-label="Open chat"
        >
          <span className="text-xl">💬</span>
        </button>
      )}
    </div>
  );
};
