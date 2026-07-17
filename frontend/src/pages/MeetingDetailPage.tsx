import React, { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { apiRequest, API_ENDPOINTS } from '../config/api';
import { AgendaItemEvidence, MeetingDetail } from '../types/meetings';
import { PDFViewer } from '../components/PDFViewer';
import { meetingTypeLabel } from '../utils/meetingLabels';

/**
 * Meeting Explorer detail view. Every agenda item renders with an
 * id="item-{number}" anchor so /meetings/:id#item-4.a is a shareable
 * deep link, and links back to the exact source PDF pages.
 */
export const MeetingDetailPage: React.FC = () => {
  const { meetingId } = useParams<{ meetingId: string }>();
  const location = useLocation();
  const [detail, setDetail] = useState<MeetingDetail | null>(null);
  const [items, setItems] = useState<AgendaItemEvidence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPdf, setShowPdf] = useState(false);

  useEffect(() => {
    if (!meetingId) return;
    setLoading(true);
    Promise.all([
      apiRequest<MeetingDetail>(API_ENDPOINTS.meetingById(Number(meetingId))),
      apiRequest<AgendaItemEvidence[]>(API_ENDPOINTS.meetingItems(Number(meetingId))),
    ])
      .then(([meetingDetail, evidenceItems]) => {
        setDetail(meetingDetail);
        setItems(evidenceItems);
        setError(null);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Failed to load meeting.')
      )
      .finally(() => setLoading(false));
  }, [meetingId]);

  // Scroll to the #item-N anchor once items have rendered
  useEffect(() => {
    if (!items.length || !location.hash) return;
    const el = document.getElementById(location.hash.slice(1));
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.add('ring-2', 'ring-blue-400', 'rounded-md');
      setTimeout(() => el.classList.remove('ring-2', 'ring-blue-400'), 4000);
    }
  }, [items, location.hash]);

  if (loading) {
    return <p className="text-gray-500 py-16 text-center">Loading meeting…</p>;
  }
  if (error || !detail) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="text-red-700">{error || 'Meeting not found.'}</p>
        <Link to="/meetings" className="text-blue-600 underline mt-4 inline-block">
          Back to meetings
        </Link>
      </div>
    );
  }

  const { meeting } = detail;
  const sourcePdf = meeting.agenda_url || meeting.minutes_url;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <nav className="text-sm mb-4">
        <Link to="/meetings" className="text-blue-600 hover:underline">
          ← All meetings
        </Link>
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">{meeting.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-gray-600">
          <span className="rounded-full bg-blue-50 text-blue-700 px-2 py-0.5">
            {meetingTypeLabel(meeting.meeting_type)}
          </span>
          <time dateTime={meeting.meeting_date}>
            {format(new Date(meeting.meeting_date), 'EEEE, MMMM d, yyyy h:mm a')}
          </time>
          {meeting.location && <span>{meeting.location}</span>}
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-sm">
          {sourcePdf && (
            <a
              href={sourcePdf}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              Source document ↗
            </a>
          )}
          {meeting.meeting_url && (
            <a
              href={meeting.meeting_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              Meeting video ↗
            </a>
          )}
          {detail.pdf_url && (
            <button
              onClick={() => setShowPdf((v) => !v)}
              className="text-blue-600 hover:underline"
            >
              {showPdf ? 'Hide document' : 'View document inline'}
            </button>
          )}
        </div>
      </header>

      {meeting.summary && (
        <section className="mb-6 rounded-md bg-gray-50 border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-1">Summary</h2>
          <p className="text-sm text-gray-700 whitespace-pre-line">{meeting.summary}</p>
        </section>
      )}

      {(meeting.key_decisions || []).length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Key decisions</h2>
          <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">
            {meeting.key_decisions!.map((decision, i) => (
              <li key={i}>{decision}</li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">
          Agenda items{items.length > 0 && ` (${items.length})`}
        </h2>
        {items.length === 0 && (
          <p className="text-sm text-gray-500">
            No structured agenda items for this meeting yet.
          </p>
        )}
        <ol className="space-y-3">
          {items.map((item) => {
            const anchor = item.item_number ? `item-${item.item_number}` : `item-id-${item.id}`;
            return (
              <li
                key={item.id}
                id={anchor}
                className="border border-gray-200 rounded-md p-4 scroll-mt-24"
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-medium text-gray-900">
                    {item.item_number && (
                      <span className="text-gray-500 mr-2">{item.item_number}.</span>
                    )}
                    {item.title}
                  </h3>
                  <a
                    href={`#${anchor}`}
                    className="text-gray-400 hover:text-blue-600 text-sm"
                    title="Link to this item"
                    aria-label={`Link to item ${item.item_number || item.id}`}
                  >
                    #
                  </a>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  {item.vote_result && (
                    <span
                      className={`rounded-full px-2 py-0.5 font-medium ${
                        /pass|approv/i.test(item.vote_result)
                          ? 'bg-green-50 text-green-700'
                          : /fail|denied/i.test(item.vote_result)
                            ? 'bg-red-50 text-red-700'
                            : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {item.vote_result}
                    </span>
                  )}
                  {item.topics.map((topic) => (
                    <span
                      key={topic}
                      className="rounded-full bg-gray-100 text-gray-600 px-2 py-0.5"
                    >
                      {topic.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>

                {item.description && (
                  <p className="mt-2 text-sm text-gray-700 whitespace-pre-line">
                    {item.description}
                  </p>
                )}

                <div className="mt-2 text-xs text-gray-500 flex flex-wrap gap-3">
                  {item.source_pdf_url && item.source_page_start && (
                    <a
                      href={item.source_pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-blue-600 underline"
                    >
                      Source: page
                      {item.source_page_end &&
                      item.source_page_end !== item.source_page_start
                        ? `s ${item.source_page_start}–${item.source_page_end}`
                        : ` ${item.source_page_start}`}{' '}
                      ↗
                    </a>
                  )}
                  {(item.entities.ordinances || []).map((ord) => (
                    <span key={ord}>Ordinance {ord}</span>
                  ))}
                  {(item.entities.districts || []).map((d) => (
                    <span key={d}>District {d}</span>
                  ))}
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      {showPdf && detail.pdf_url && (
        <section className="mt-8">
          <PDFViewer pdfUrl={detail.pdf_url} meetingTitle={meeting.title} />
        </section>
      )}
    </div>
  );
};
