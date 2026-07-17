import '@testing-library/jest-dom';

// jsdom does not implement scrollIntoView
Element.prototype.scrollIntoView = () => {};
