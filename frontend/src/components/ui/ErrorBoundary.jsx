import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-box" style={{ margin: 24, padding: 20 }}>
          <h3 style={{ margin: '0 0 8px', color: 'var(--accent-red)' }}>
            <i className="ti ti-alert-triangle" style={{ marginRight: 6 }} />
            Something went wrong
          </h3>
          <p style={{ fontSize: 13, color: 'var(--text-dim)', margin: '0 0 12px' }}>
            {this.state.error.message}
          </p>
          <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
