import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { apiRequest } from '../config/api';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';

/**
 * Video + transcript + translation + comments panel for a meeting.
 *
 * - The video and transcript are synced both ways: clicking a segment
 *   seeks the video; playback highlights and scrolls to the segment
 *   being spoken.
 * - Language toggle shows Spanish (or any available) translations
 *   produced by the media pipeline.
 * - Comments are posted by signed-in residents and can be anchored to
 *   the current video moment.
 */

interface TranscriptSegment {
  index: number;
  start: number;
  end: number;
  text: string;
  translated: string | null;
  video_link: string | null;
}

interface TranscriptResponse {
  meeting_id: number;
  video_url: string | null;
  segment_count: number;
  languages: string[];
  segments: TranscriptSegment[];
}

interface MeetingCommentItem {
  id: number;
  display_name: string;
  content: string;
  video_timestamp: number | null;
  created_at: string;
}

const LANGUAGE_LABELS: Record<string, string> = { es: 'Español' };

const formatTime = (seconds: number): string => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
};

export const MeetingMediaPanel: React.FC<{ meetingId: number }> = ({ meetingId }) => {
  const { user } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);

  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [language, setLanguage] = useState<string>('original');
  const [search, setSearch] = useState('');
  const [currentTime, setCurrentTime] = useState(0);
  const [followPlayback, setFollowPlayback] = useState(true);

  const [comments, setComments] = useState<MeetingCommentItem[]>([]);
  const [newComment, setNewComment] = useState('');
  const [anchorToVideo, setAnchorToVideo] = useState(false);
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    setTranscript(null);
    setLanguage('original');
    setSearch('');
    const load = async () => {
      try {
        const lang = 'es'; // request translations up front; toggle is client-side
        const data = await apiRequest<TranscriptResponse>(
          `/api/v1/meetings/${meetingId}/transcript?lang=${lang}`
        );
        setTranscript(data);
      } catch {
        setTranscript(null); // no transcript yet — panel stays hidden
      }
      try {
        const data = await apiRequest<{ comments: MeetingCommentItem[] }>(
          `/api/v1/meetings/${meetingId}/comments`
        );
        setComments(data.comments);
      } catch {
        setComments([]);
      }
    };
    load();
  }, [meetingId]);

  const filteredSegments = useMemo(() => {
    if (!transcript) return [];
    if (!search.trim()) return transcript.segments;
    const needle = search.toLowerCase();
    return transcript.segments.filter(
      (segment) =>
        segment.text.toLowerCase().includes(needle) ||
        (segment.translated || '').toLowerCase().includes(needle)
    );
  }, [transcript, search]);

  const activeIndex = useMemo(() => {
    if (!transcript) return -1;
    return transcript.segments.findIndex(
      (segment) => currentTime >= segment.start && currentTime < segment.end
    );
  }, [transcript, currentTime]);

  useEffect(() => {
    if (followPlayback && activeRef.current) {
      activeRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [activeIndex, followPlayback]);

  const seekTo = useCallback((seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      videoRef.current.play().catch(() => undefined);
    }
  }, []);

  const postComment = async () => {
    if (!newComment.trim()) return;
    setPosting(true);
    try {
      await apiRequest(`/api/v1/meetings/${meetingId}/comments`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({
          content: newComment.trim(),
          video_timestamp:
            anchorToVideo && videoRef.current ? videoRef.current.currentTime : null,
        }),
      });
      setNewComment('');
      const data = await apiRequest<{ comments: MeetingCommentItem[] }>(
        `/api/v1/meetings/${meetingId}/comments`
      );
      setComments(data.comments);
      toast.success('Comment posted');
    } catch {
      toast.error('Could not post comment');
    } finally {
      setPosting(false);
    }
  };

  const hasMedia = transcript && (transcript.video_url || transcript.segment_count > 0);
  if (!hasMedia && comments.length === 0 && !user) return null;

  return (
    <div className="p-6 border-b border-gray-200">
      <h3 className="text-lg font-medium text-gray-900 mb-4">
        🎬 Meeting Video &amp; Transcript
      </h3>

      {transcript?.video_url && (
        <video
          ref={videoRef}
          controls
          preload="metadata"
          className="w-full rounded-lg mb-4 bg-black"
          src={transcript.video_url}
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        />
      )}

      {transcript && transcript.segment_count > 0 && (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search the transcript…"
              className="flex-1 min-w-[180px] border border-gray-300 rounded-md px-3 py-1.5 text-sm"
            />
            {transcript.languages.length > 0 && (
              <div className="flex rounded-md border border-gray-300 overflow-hidden text-sm">
                <button
                  className={`px-3 py-1.5 ${language === 'original' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => setLanguage('original')}
                >
                  English
                </button>
                {transcript.languages.map((code) => (
                  <button
                    key={code}
                    className={`px-3 py-1.5 ${language === code ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'}`}
                    onClick={() => setLanguage(code)}
                  >
                    {LANGUAGE_LABELS[code] || code.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
            <label className="flex items-center gap-1 text-xs text-gray-600">
              <input
                type="checkbox"
                checked={followPlayback}
                onChange={(e) => setFollowPlayback(e.target.checked)}
              />
              Follow playback
            </label>
          </div>

          <div className="max-h-72 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
            {filteredSegments.map((segment) => {
              const isActive = segment.index === activeIndex;
              const display =
                language !== 'original' && segment.translated
                  ? segment.translated
                  : segment.text;
              return (
                <button
                  key={segment.index}
                  ref={isActive ? activeRef : undefined}
                  onClick={() => seekTo(segment.start)}
                  className={`w-full text-left px-3 py-2 text-sm flex gap-3 hover:bg-blue-50 ${
                    isActive ? 'bg-blue-100' : 'bg-white'
                  }`}
                >
                  <span className="text-blue-600 font-mono text-xs whitespace-nowrap pt-0.5">
                    {formatTime(segment.start)}
                  </span>
                  <span className="text-gray-800">{display}</span>
                </button>
              );
            })}
            {filteredSegments.length === 0 && (
              <div className="px-3 py-4 text-sm text-gray-500">
                No transcript lines match "{search}".
              </div>
            )}
          </div>
          <div className="mt-1 text-xs text-gray-400">
            Automated transcript — may contain errors. Click a line to jump the
            video to that moment.
          </div>
        </>
      )}

      {/* Comments */}
      <div className="mt-6">
        <h4 className="text-md font-medium text-gray-900 mb-3">
          💬 Resident Comments ({comments.length})
        </h4>
        <div className="space-y-3 mb-4">
          {comments.map((comment) => (
            <div key={comment.id} className="bg-gray-50 rounded-lg p-3">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span className="font-medium text-gray-700">{comment.display_name}</span>
                <span>
                  {comment.video_timestamp !== null && (
                    <button
                      className="text-blue-600 hover:underline mr-2"
                      onClick={() => seekTo(comment.video_timestamp as number)}
                    >
                      ▶ {formatTime(comment.video_timestamp)}
                    </button>
                  )}
                  {new Date(comment.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="text-sm text-gray-800">{comment.content}</div>
            </div>
          ))}
          {comments.length === 0 && (
            <div className="text-sm text-gray-500">No comments yet.</div>
          )}
        </div>

        {user ? (
          <div>
            <textarea
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              rows={2}
              placeholder="Share your perspective on this meeting…"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            />
            <div className="flex items-center justify-between mt-2">
              <label className="flex items-center gap-1 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={anchorToVideo}
                  onChange={(e) => setAnchorToVideo(e.target.checked)}
                  disabled={!transcript?.video_url}
                />
                Link to current video moment
              </label>
              <button
                onClick={postComment}
                disabled={posting || !newComment.trim()}
                className="bg-blue-600 text-white text-sm px-4 py-1.5 rounded-md disabled:opacity-50"
              >
                {posting ? 'Posting…' : 'Post comment'}
              </button>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-500">
            Sign in to join the conversation.
          </div>
        )}
      </div>
    </div>
  );
};
