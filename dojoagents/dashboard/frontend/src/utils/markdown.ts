// markdown-it configuration
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
})

export function renderMarkdown(text: string): string {
  return md.render(text)
}

export default md
