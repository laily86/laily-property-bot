# Semakan integrasi rasmi — 19 Oktober 2026

**Keputusan: kedua-dua penyambung dinyahaktifkan dan berstatus `INTEGRATION_UNAVAILABLE`.**
Ini bermakna sokongan belum dapat disahkan, bukan kesimpulan bahawa platform tidak pernah menyediakan API sedemikian.

## Bukti dan had penyelidikan

Permintaan baca HTTPS dibuat dari persekitaran pembangunan ke:

- https://www.mudah.my/
- https://www.mudah.my/pro-niaga
- https://developers.facebook.com/docs/commerce-platform/
- https://www.facebook.com/help/561376580709359

Keempat-empat permintaan disekat oleh proksi rangkaian: `Tunnel connection failed: 403 Forbidden`.
Kandungan dokumentasi tidak berjaya dibaca; pautan di atas ialah sasaran semakan, bukan bukti kelulusan API.
Tiada kelayakan akaun atau sesi pelayar digunakan. Tiada permintaan tulis dihantar ke platform.

## Mudah.my PRO Niaga

Pemilik menyatakan akaun mempunyai fungsi **Add Draft**. Butang antaramuka itu tidak membuktikan hak
akses programatik. Sebelum penyambung akaun boleh dibangunkan, dapatkan dokumentasi atau pengesahan
bertulis daripada sokongan PRO Niaga mengenai API rasmi untuk **mencipta dan menyimpan draf peribadi**,
kaedah pengesahan, skop akses, had kadar, syarat penggunaan serta cara membuktikan status tidak diterbitkan.
Jangan gunakan endpoint dalaman yang diperoleh daripada trafik pelayar.

## Facebook Marketplace

API Facebook Page, Page unpublished posts, katalog Commerce dan Marketplace property listings bukan objek yang sama.
Tiada kaedah rasmi untuk aplikasi pihak ketiga menyimpan draf peribadi **Marketplace hartanah milik pengguna**
telah disahkan dalam projek ini. Sebarang akses rakan kongsi perlu dinilai berdasarkan kelayakan sebenar akaun,
jenis listing dan kebenaran rasmi. Jangan gunakan API Page sebagai pengganti.

## Syarat perubahan masa depan

Pembangunan penyambung memerlukan tugasan berasingan dengan bukti rasmi yang boleh diperiksa,
authentication yang dibenarkan dan ujian bahawa iklan tidak kelihatan umum atau dihantar untuk semakan.
Walaupun API draf dibenarkan, jangan tambah fungsi publish/activate/boost/schedule/submit.
Jika sesuatu operasi mungkin menerbitkan iklan, berhenti.

Versi ini tidak menerima cookies, kata laluan platform, token platform atau sesi pelayar.
`PLATFORM_DRAFT_SAVED` ialah status yang dikhaskan sahaja dan tidak pernah dihasilkan oleh aplikasi ini.
Tiada pautan draf akaun direka. ZIP hanyalah pakej manual, bukan bukti draf akaun.
