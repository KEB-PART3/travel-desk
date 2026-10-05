/* Travel Desk — PHOTOS registry.
   This is install-specific data, like trips.json: photos.js is git-ignored
   and seeded from photos.example.js on first deploy. autopopulate-images.py
   writes new entries here; check-logos.py reads pad values from here.
   Loaded by index.html as a classic script before the app script. */
const PHOTOS={
  /* Your images live in img/ and are registered here. Events reference a
     registry key, never a path — swapping an image is a one-line edit.
     Photo example:
       'my-hotel':{src:'img/my-hotel.jpg',
         alt:'What the photo actually shows — write it from opening the file'},
     Logo example (contain-fit on a light tile, never cropped):
       'my-airline':{src:'img/my-airline.png',fit:'contain',tile:'light',
         alt:'Airline logo description'},
     Run ./check-logos.py after adding a logo — it measures the padding each
     logo needs and fails the deploy if a mark would be clipped. */
  /* sample-trip placeholders (generated images, committed with the repo) */
  'sample-portland':{src:'img/sample-portland.jpg',
    alt:'Placeholder image for the Portland sample trip'},
  'sample-aspen':{src:'img/sample-aspen.jpg',
    alt:'Placeholder image for the Aspen sample trip'},
};
