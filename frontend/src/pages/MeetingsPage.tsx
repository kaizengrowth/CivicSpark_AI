import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { apiRequest, API_ENDPOINTS } from '../config/api';
import { Meeting } from '../types/meetings';
import { StalenessBanner } from '../components/StalenessBanner';
import { PageHeader } from '@/components/PageHeader';
import { meetingTypeLabel } from '../utils/meetingLabels';

interface MeetingListResponse {
  items?: Meeting[];
  data?: Meeting[];
  total?: number;
}

export const MeetingsPage: React.FC = () => {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'upcoming' | 'completed'>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  const fetchMeetings = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<MeetingListResponse | Meeting[]>(
        `${API_ENDPOINTS.meetings}?limit=200`
      );
      const items = Array.isArray(response)
        ? response
        : response.items || response.data || [];
      setMeetings(items);
    } catch (err) {
      // Honest failure: no sample-data fallback pretending to be live
      setError(
        err instanceof Error ? err.message : 'Failed to load meetings from the server.'
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMeetings();
  }, []);

  const meetingTypes = useMemo(
    () => Array.from(new Set(meetings.map((m) => m.meeting_type))).sort(),
    [meetings]
  );

  const filtered = useMemo(() => {
    const now = new Date();
    return meetings
      .filter((m) => {
        if (typeFilter !== 'all' && m.meeting_type !== typeFilter) return false;
        const date = new Date(m.meeting_date);
        if (statusFilter === 'upcoming' && date < now) return false;
        if (statusFilter === 'completed' && date >= now) return false;
        if (searchTerm) {
          const haystack = [
            m.title,
            m.summary,
            ...(m.topics || []),
            ...(m.keywords || []),
          ]
            .join(' ')
            .toLowerCase();
          if (!haystack.includes(searchTerm.toLowerCase())) return false;
        }
        return true;
      })
      .sort(
        (a, b) =>
          new Date(b.meeting_date).getTime() - new Date(a.meeting_date).getTime()
      );
  }, [meetings, searchTerm, statusFilter, typeFilter]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <PageHeader
        title="City Meetings"
        description="Agendas, minutes, and decisions from Tulsa city government — every item linked to its source document."
      />

      <StalenessBanner />

      <div className="flex flex-wrap gap-3 mb-6">
        <input
          type="search"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search meetings and topics…"
          className="flex-1 min-w-[220px] rounded-md border border-gray-300 px-3 py-2 text-sm"
          aria-label="Search meetings"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          aria-label="Filter by status"
        >
          <option value="all">All meetings</option>
          <option value="upcoming">Upcoming</option>
          <option value="completed">Past</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          aria-label="Filter by meeting type"
        >
          <option value="all">All bodies</option>
          {meetingTypes.map((t) => (
            <option key={t} value={t}>
              {meetingTypeLabel(t)}
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="text-gray-500 py-12 text-center">Loading meetings…</p>}

      {error && !loading && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-medium">Couldn't load meetings.</p>
          <p className="mt-1">{error}</p>
          <button
            onClick={fetchMeetings}
            className="mt-3 rounded-md bg-red-100 px-3 py-1.5 font-medium hover:bg-red-200"
          >
            Try again
          </button>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <p className="text-gray-500 py-12 text-center">
          No meetings match your filters
          {meetings.length === 0 &&
            ' — the corpus may still be ingesting from the City of Tulsa'}
          .
        </p>
      )}

      <ul className="divide-y divide-gray-200">
        {filtered.map((meeting) => (
          <li key={meeting.id}>
            <Link
              to={`/meetings/${meeting.id}`}
              className="block py-4 px-2 hover:bg-gray-50 rounded-md"
            >
              <div className="flex items-baseline justify-between gap-4">
                <h3 className="font-medium text-gray-900">{meeting.title}</h3>
                <time
                  dateTime={meeting.meeting_date}
                  className="text-sm text-gray-500 whitespace-nowrap"
                >
                  {format(new Date(meeting.meeting_date), 'MMM d, yyyy h:mm a')}
                </time>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full bg-blue-50 text-blue-700 px-2 py-0.5">
                  {meetingTypeLabel(meeting.meeting_type)}
                </span>
                {(meeting.topics || []).slice(0, 4).map((topic) => (
                  <span
                    key={topic}
                    className="rounded-full bg-gray-100 text-gray-600 px-2 py-0.5"
                  >
                    {topic.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
              {meeting.summary && (
                <p className="mt-1 text-sm text-gray-600 line-clamp-2">
                  {meeting.summary}
                </p>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
};
