sh scripts/build.sh
python -m http.server 4173 --directory build

echo "serving at http://localhost:4173/jcvb"
