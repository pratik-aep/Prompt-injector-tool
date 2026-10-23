import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { AppStateProvider } from '../hooks/useAppState'

export const renderPage = (ui: ReactElement, route = '/') =>
  render(<MemoryRouter initialEntries={[route]}><AppStateProvider>{ui}</AppStateProvider></MemoryRouter>)
