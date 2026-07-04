import sys
import argparse
import logging
from organizer.processor import FileOrganizer

# Try importing colorlog for beautiful colored terminal output
try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False


def setup_logging(verbose: bool = False):
    """Configures application-wide logging formats."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    if HAS_COLORLOG:
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s[%(levelname)s] %(message)s",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        # Remove any default handlers to avoid duplicate logs
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
        root_logger.addHandler(handler)
    else:
        # Fallback to standard logging formatting
        logging.basicConfig(
            level=log_level,
            format="[%(levelname)s] %(message)s",
            stream=sys.stdout
        )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Organizador de Arquivos Inteligente para macOS. Reorganiza fotos, vídeos, áudios e documentos com metadados, geocodificação e IA."
    )
    
    # Required arguments
    parser.add_argument(
        "--src",
        required=True,
        help="Pasta de origem contendo os arquivos a serem organizados."
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Pasta de destino base onde a estrutura de pastas organizada será criada."
    )

    # Optional styling arguments
    parser.add_argument(
        "--folder-format",
        default="{year}/{month}",
        help="Template para a estrutura de pastas. Ex: '{country}/{year}' ou '{year}/{month}' (Padrão: '{year}/{month}')."
    )
    parser.add_argument(
        "--file-format",
        default="{original_name}",
        help="Template para renomear os arquivos. Ex: '{ai_tag}_{original_name}' (Padrão: '{original_name}')."
    )

    # Optional flags and action configuration
    parser.add_argument(
        "--ai-rename",
        action="store_true",
        help="Ativa a análise de imagem por IA (Visão Computacional) para incluir tags descritivas no nome do arquivo."
    )
    parser.add_argument(
        "--action",
        choices=["copy", "move"],
        default="copy",
        help="Ação a ser executada para a reorganização: 'copy' (copiar) ou 'move' (mover). (Padrão: 'copy')."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo de segurança. Simula e imprime a estrutura que seria criada sem de fato realizar cópias/movimentações de arquivo."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita o processamento ao número especificado de arquivos."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Exibe logs de depuração detalhados (debug level)."
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(args.verbose)

    # Validate directories are not overlapping
    import os
    src_abs = os.path.abspath(args.src)
    dest_abs = os.path.abspath(args.dest)

    if src_abs == dest_abs:
        logging.critical("A pasta de origem e a pasta de destino não podem ser as mesmas.")
        sys.exit(1)

    # Instantiate and run the organizer
    organizer = FileOrganizer(
        src=args.src,
        dest=args.dest,
        folder_format=args.folder_format,
        file_format=args.file_format,
        action=args.action,
        ai_rename=args.ai_rename,
        dry_run=args.dry_run,
        limit=args.limit
    )

    try:
        organizer.run()
    except Exception as e:
        logging.critical(f"Falha crítica na execução do organizador: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
