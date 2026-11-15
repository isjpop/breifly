import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ScrollToTop } from './components/ScrollToTop'
import { ArticlePage } from './pages/ArticlePage'
import { BriefingPage } from './pages/BriefingPage'
import { CategoryPage } from './pages/CategoryPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { SearchPage } from './pages/SearchPage'

export function AppRoutes() {
  return (
    <Layout>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<BriefingPage />} />
        <Route path="/category/:slug" element={<CategoryPage />} />
        <Route path="/article/:id" element={<ArticlePage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
