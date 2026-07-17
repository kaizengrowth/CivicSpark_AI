const MEETING_TYPE_LABELS: Record<string, string> = {
  regular_council: 'City Council',
  city_council: 'City Council',
  public_works_committee: 'Public Works Committee',
  urban_economic_committee: 'Urban & Economic Development',
  budget_committee: 'Budget Committee',
  planning_commission: 'Planning Commission',
  board_of_adjustment: 'Board of Adjustment',
  other: 'Other',
};

export const meetingTypeLabel = (type: string): string =>
  MEETING_TYPE_LABELS[type] ||
  type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
