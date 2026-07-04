import zipfile
import xml.etree.ElementTree as ET
import os
from pypdf import PdfReader

base_dir = "/Volumes/Midia/Livros"

def get_epub_metadata(epub_path):
    try:
        with zipfile.ZipFile(epub_path, 'r') as epub:
            container_xml = epub.read('META-INF/container.xml')
            root = ET.fromstring(container_xml)
            namespaces = {'ns': 'urn:oasis:names:tc:opendocument:xmlns:container'}
            rootfile = root.find('.//ns:rootfile', namespaces)
            if rootfile is None:
                return None
            opf_path = rootfile.attrib['full-path']
            
            opf_xml = epub.read(opf_path)
            opf_root = ET.fromstring(opf_xml)
            ns = {
                'opf': 'http://www.idpf.org/2007/opf',
                'dc': 'http://purl.org/dc/elements/1.1/'
            }
            title_el = opf_root.find('.//dc:title', ns)
            creator_el = opf_root.find('.//dc:creator', ns)
            title = title_el.text if title_el is not None else "Unknown Title"
            author = creator_el.text if creator_el is not None else "Unknown Author"
            return {"title": title, "author": author}
    except Exception as e:
        return {"error": str(e)}

def get_pdf_metadata(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        meta = reader.metadata
        title = meta.title if meta and meta.title else ""
        author = meta.author if meta and meta.author else ""
        
        first_page_text = ""
        if len(reader.pages) > 0:
            first_page_text = reader.pages[0].extract_text() or ""
            
        return {
            "title": title,
            "author": author,
            "sample": first_page_text[:400].strip().replace("\n", " ")
        }
    except Exception as e:
        return {"error": str(e)}

for file in os.listdir(base_dir):
    if file.startswith("."):
        continue
    file_path = os.path.join(base_dir, file)
    _, ext = os.path.splitext(file)
    ext = ext.lower()
    
    print(f"=== File: {file} ===")
    if ext == ".epub":
        print(get_epub_metadata(file_path))
    elif ext == ".pdf":
        print(get_pdf_metadata(file_path))
    print()
