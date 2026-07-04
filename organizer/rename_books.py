import os

base_dir = "/Volumes/Midia/Livros"

# Definindo o mapeamento de renomeação exato e validado dos 11 livros
BOOK_MAP = {
    "_OceanofPDF.com_Here_n_Hereafter_-_Tyler_Henry.pdf": "Tyler Henry - Here & Hereafter.pdf",
    "862729125-Bruxa-Psiquica-Um-Guia-Metafisico-Para-Meditacao-Magia-e-Manifestacao-TOAZ-info.pdf": "Mat Auryn - Bruxa Psíquica.pdf",
    "802013274-A-Arte-Psiquica-Tarot-Mat-Auryn-Z-Library-1.pdf": "Mat Auryn - A Arte Psíquica do Tarô.pdf",
    "PSYCHIC-WITCH-AUDIOBOOK-COMPANION.pdf": "Mat Auryn - Psychic Witch Audiobook Companion.pdf",
    "_OceanofPDF.com_Mastering_Magick_-_Mat_Auryn.pdf": "Mat Auryn - Mastering Magick.pdf",
    "MASTERING-MAGICK-AUDIOBOOK-COMPANION-v2.pdf": "Mat Auryn - Mastering Magick Audiobook Companion.pdf",
    "THE-PSYCHIC-ART-OF-TAROT-AUDIO-COMPANION.pdf": "Mat Auryn - The Psychic Art of Tarot Audio Companion.pdf",
    "_OceanofPDF.com_Medium_Mentor_-_Maryann_Dimarco.pdf": "Maryann DiMarco - Medium Mentor.pdf",
    "859335632-Awakening-Your-Psychic-Ability-A-Practical-Guide-to-Develop-Your-Intuition-Demystify-the-Spiritual-World-and-Open-Your-Psychic-Senses-Best-Quality.pdf": "Lisa Campion - Awakening Your Psychic Ability.pdf",
    "Ready, Fire, Aim_ Zero to $100 Million in No Time Flat by Michael Masterson.pdf": "Michael Masterson - Ready, Fire, Aim.pdf",
    "Ready, Fire, Aim How I Turned a Hobby Into an Empire.epub": "Melissa Carbone - Ready, Fire, Aim.epub"
}

def print_progress_bar(current, total):
    percent = float(current) / total
    bar_length = 30
    arrow = '█' * int(percent * bar_length)
    spaces = '░' * (bar_length - len(arrow))
    import sys
    sys.stdout.write(f"\rProgresso: [{arrow}{spaces}] {current}/{total} ({percent*100:.1f}%)")
    sys.stdout.flush()
    if current == total:
        sys.stdout.write("\n")
        sys.stdout.flush()

def rename_books():
    print(f"Iniciando a renomeação de livros em: {base_dir}")
    
    total = len(BOOK_MAP)
    processed = 0
    errors = 0
    
    for orig_name, new_name in BOOK_MAP.items():
        src_path = os.path.join(base_dir, orig_name)
        dest_path = os.path.join(base_dir, new_name)
        
        # Se o arquivo de origem existe, faz a renomeação
        if os.path.exists(src_path):
            try:
                # Se o destino já existe por algum motivo, removemos/substituímos ou renomeamos com segurança
                if os.path.exists(dest_path) and src_path != dest_path:
                    os.remove(dest_path)
                os.rename(src_path, dest_path)
                import sys
                sys.stdout.write("\r\033[K")
                print(f"Renomeado '{orig_name}' -> '{new_name}'")
            except Exception as e:
                import sys
                sys.stdout.write("\r\033[K")
                print(f"Erro ao renomear '{orig_name}': {e}")
                errors += 1
        else:
            # Caso já tenha sido renomeado em execuções anteriores, apenas pulamos graciosamente
            import sys
            sys.stdout.write("\r\033[K")
            if os.path.exists(dest_path):
                print(f"Arquivo já estava renomeado: '{new_name}'")
            else:
                print(f"Arquivo original não encontrado: '{orig_name}'")
                errors += 1
                
        processed += 1
        print_progress_bar(processed, total)
        
    print("\n=== Renomeação Concluída ===")
    print(f"Total mapeado: {total}")
    print(f"Renomeados com sucesso: {total - errors}")
    print(f"Erros encontrados: {errors}")

if __name__ == "__main__":
    rename_books()
