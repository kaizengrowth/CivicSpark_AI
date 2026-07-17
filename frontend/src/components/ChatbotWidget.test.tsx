import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { ChatbotWidget } from './ChatbotWidget';

const mockApiRequest = vi.fn();
vi.mock('../config/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../config/api')>();
  return { ...actual, apiRequest: (...args: unknown[]) => mockApiRequest(...args) };
});

const openAndSend = async (text: string) => {
  fireEvent.click(screen.getByLabelText('Open chat'));
  fireEvent.change(screen.getByPlaceholderText(/Ask about Tulsa/i), {
    target: { value: text },
  });
  fireEvent.click(screen.getByText('Send'));
};

describe('ChatbotWidget', () => {
  beforeEach(() => mockApiRequest.mockReset());

  test('renders citations with deep links', async () => {
    mockApiRequest.mockResolvedValue({
      response: 'The franchise fee is $2,500,000 per year [c:7].',
      success: true,
      status: 'answered',
      citations: [
        {
          chunk_id: 7,
          quote: 'fee of $2,500,000 per year',
          source_url: 'https://tulsa-ok.granicus.com/agenda/1',
          deep_link: '/meetings/2#item-4.a',
          meeting_title: 'Regular Council Meeting',
          meeting_date: '2026-07-01',
          item_number: '4.a',
          page: 3,
        },
      ],
      unsupported_claims: [],
    });

    render(
      <MemoryRouter>
        <ChatbotWidget />
      </MemoryRouter>
    );
    await openAndSend('How much is the franchise fee?');

    await waitFor(() => {
      expect(screen.getByText(/view item/)).toBeInTheDocument();
    });
    expect(screen.getByText(/view item/).getAttribute('href')).toBe(
      '/meetings/2#item-4.a'
    );
    expect(screen.getByText(/Regular Council Meeting/)).toBeInTheDocument();
  });

  test('shows distinct refusal state', async () => {
    mockApiRequest.mockResolvedValue({
      response: "The records I have don't contain enough evidence.",
      success: true,
      status: 'refused',
      citations: [],
      unsupported_claims: [],
    });

    render(
      <MemoryRouter>
        <ChatbotWidget />
      </MemoryRouter>
    );
    await openAndSend('What is the mayor’s favorite color?');

    await waitFor(() => {
      expect(
        screen.getByText('No verified answer available')
      ).toBeInTheDocument();
    });
  });

  test('reports stripped unverified claims', async () => {
    mockApiRequest.mockResolvedValue({
      response: 'The item passed [c:7].',
      success: true,
      status: 'partial',
      citations: [{ chunk_id: 7, quote: 'passed' }],
      unsupported_claims: ['The budget is $9,999,999 (numeric token not in source)'],
    });

    render(
      <MemoryRouter>
        <ChatbotWidget />
      </MemoryRouter>
    );
    await openAndSend('Did it pass and how much?');

    await waitFor(() => {
      expect(screen.getByText(/unverified claim/)).toBeInTheDocument();
    });
  });
});
