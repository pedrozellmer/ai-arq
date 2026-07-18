/** Config do Tailwind pro CSS COMPILADO (substitui o Play CDN — 18/07/2026).
 *  O Play CDN (~350KB de JS) gerava o CSS em runtime no celular do visitante,
 *  a cada visita. Agora o CSS é gerado UMA vez e servido estático.
 *
 *  Pra regenerar depois de criar classe nova: rode gerar-css.bat (Windows).
 *  O scan pega classes em HTML e nas template literals dos .js — classe
 *  CONCATENADA dinamicamente ('bg-' + cor) NÃO é detectada; se precisar,
 *  adicione na safelist abaixo.
 */
module.exports = {
  content: [
    "./*.html",
    "./*.js",
    "./blog/**/*.html",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
