import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import App from './App';

// pdfjs requires DOMMatrix, which jsdom does not provide
vi.mock('react-pdf', () => ({
  Document: () => null,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: {}, version: 'test' },
}));

vi.mock('./config/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./config/api')>();
  return {
    ...actual,
    apiRequest: vi.fn().mockRejectedValue(new Error('no network in tests')),
  };
});

describe('App', () => {
  test('renders the home page shell', () => {
    render(<App />);
    expect(document.querySelector('div')).toBeInTheDocument();
    // The layout navigation should be present on the home route
    expect(screen.getAllByRole('link').length).toBeGreaterThan(0);
  });
});
