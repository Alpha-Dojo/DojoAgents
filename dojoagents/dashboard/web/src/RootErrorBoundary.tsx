import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class RootErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Alpha Dojo render error', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            padding: 24,
            color: '#ffb4b4',
            fontFamily: 'system-ui, sans-serif',
            whiteSpace: 'pre-wrap',
          }}
        >
          <strong>Alpha Dojo failed to load</strong>
          {'\n\n'}
          {this.state.error.message}
        </div>
      );
    }
    return this.props.children;
  }
}
